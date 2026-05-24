"""Process an AutoPkg report plist: report results to the API and ingest pkginfo.

Expected environment variables:
    API_BASE_URL  - e.g. https://example.ngrok-free.app
    RUN_ID        - UUID of the AutoPkg run
    REPORT_FILE   - path to the report plist
    PKGSINFO_DIR  - path to the pkgsinfo directory
"""

import json
import os
import plistlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime


def make_serializable(obj):
    """Recursively convert plist-native types to JSON-safe equivalents."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_serializable(v) for v in obj]
    return obj


def imported_display_title(item, pkgsinfo_dir, recipe_name):
    """Human-facing title for approvals UI (pkg display name, not report filename)."""
    name = item.get("display_name") or item.get("name")
    if name:
        return str(name)
    pkginfo_path = item.get("pkginfo_path", "")
    if pkginfo_path and pkgsinfo_dir:
        full_path = os.path.join(pkgsinfo_dir, pkginfo_path)
        if os.path.exists(full_path):
            with open(full_path, "rb") as pf:
                pkginfo_dict = plistlib.load(pf)
            return str(
                pkginfo_dict.get("display_name")
                or pkginfo_dict.get("name")
                or recipe_name
            )
    return recipe_name


def _json_headers():
    h = {"Content-Type": "application/json"}
    token = os.environ.get("AUTOMUNKI_API_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _report_stem(report_path: str) -> str:
    base = os.path.basename(report_path)
    if base.lower().endswith(".plist"):
        return base[:-6]
    return base


def _identifier_from_report_plist(report: dict) -> str | None:
    """Best-effort recipe Identifier from report body (runner / AutoPkg variants)."""
    for key in ("Identifier", "identifier", "recipe_identifier"):
        v = report.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    rec = report.get("recipe")
    if isinstance(rec, dict):
        v = rec.get("Identifier") or rec.get("identifier")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _find_identifier_deep(obj: object, depth: int = 0) -> str | None:
    """Walk report plist; AutoPkg often nests Identifier under summary/input dicts."""
    if depth > 14:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("Identifier", "identifier") and isinstance(v, str):
                s = v.strip()
                if s.startswith("local.munki.") or s.startswith("com.github."):
                    return s
                if s.startswith("com.") and s.count(".") >= 3:
                    return s
            found = _find_identifier_deep(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_identifier_deep(v, depth + 1)
            if found:
                return found
    return None


def _recipe_file_from_cloud_runner_report_name(report_path: str) -> str | None:
    """``report_YYMMDD_HHMM_Recipe.munki.recipe.plist`` → ``Recipe.munki.recipe``."""
    base = os.path.basename(report_path)
    m = re.match(r"^report_\d+_\d+_(.+)\.plist$", base, re.IGNORECASE)
    return m.group(1) if m else None


def _autopkg_runner_log_path() -> str | None:
    """Path to ``cloud-autopkg-runner`` log (same run as this report)."""
    env = os.environ.get("AUTOPKG_RUNNER_LOG", "").strip()
    if env and os.path.isfile(env):
        return env
    ws = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if ws:
        candidate = os.path.join(ws, "autopkg_runner.log")
        if os.path.isfile(candidate):
            return candidate
    return None


def _recipe_error_tags_for_log(report_path: str) -> list[str]:
    """Substrings that appear in cloud-autopkg-runner ERROR lines for this recipe."""
    tags: list[str] = []
    cr = _recipe_file_from_cloud_runner_report_name(report_path)
    if cr:
        if cr.endswith(".recipe"):
            tags.append(cr[: -len(".recipe")])
        tags.append(cr)
    stem = _report_stem(report_path)
    if stem.startswith("local.munki."):
        rest = stem[len("local.munki.") :]
        if rest:
            tags.append(rest)
            if not rest.endswith(".munki"):
                tags.append(f"{rest}.munki")
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _failure_from_autopkg_runner_log(report_path: str) -> str | None:
    """When AutoPkg's report plist omits ``failures``, the runner still logs ERROR lines.

    cloud-autopkg-runner runs ``autopkg`` with a non-zero exit on check/full failure but
    still merges the report plist, which may have empty ``failures`` — we recover the
    message from the runner log (written with mode ``w`` per run).

    Only lines that look like **real** runner failures are counted (see
    ``_CLOUD_RUNNER_LOG_FAILURE_MARKERS``). Bare ``ERROR`` substrings or unrelated
    log noise must not flip a successful ``no_change`` run to ``failed``.
    """
    log_path = _autopkg_runner_log_path()
    if not log_path:
        return None
    tags = _recipe_error_tags_for_log(report_path)
    if not tags:
        return None
    errors: list[str] = []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "ERROR" not in line:
                    continue
                if not any(tag in line for tag in tags):
                    continue
                if not any(m in line for m in _CLOUD_RUNNER_LOG_FAILURE_MARKERS):
                    continue
                s = line.strip()
                if s and s not in errors:
                    errors.append(s)
    except OSError:
        return None
    if not errors:
        return None
    return "; ".join(errors)


# Phrases cloud-autopkg-runner uses on real failures (not benign ERROR-level noise).
_CLOUD_RUNNER_LOG_FAILURE_MARKERS: tuple[str, ...] = (
    "An error occurred",
    "Worker failed unexpectedly",
    "timed out",
)


def _duration_seconds_from_report(report: dict) -> int | None:
    """Sum processor ``time`` fields from AutoPkg ``summary_results`` (seconds)."""
    summary = report.get("summary_results")
    if not isinstance(summary, dict):
        return None
    total = 0.0
    found = False
    for block in summary.values():
        if not isinstance(block, dict):
            continue
        t = block.get("time")
        if isinstance(t, str):
            try:
                t = float(t)
            except ValueError:
                continue
        if isinstance(t, (int, float)) and t >= 0:
            total += float(t)
            found = True
    if not found:
        return None
    return max(1, int(round(total)))


def recipe_identifier_and_name(report_path: str, report: dict) -> tuple[str, str]:
    """
    (recipe_identifier, recipe_name) for API / DB matching.

    Report files are often named like ``local.munki.Blender.plist`` (full identifier).
    The old logic always prepended ``local.munki.``, producing a bogus identifier and
    breaking ``last_run_*`` updates on the recipe row.
    """
    stem = _report_stem(report_path)
    ident = _identifier_from_report_plist(report) or _find_identifier_deep(report)
    if ident:
        if ident.startswith("local.munki."):
            name = ident[len("local.munki.") :]
        else:
            name = stem
        return ident, name
    cr_recipe = _recipe_file_from_cloud_runner_report_name(report_path)
    if cr_recipe and cr_recipe.endswith(".munki.recipe"):
        product = cr_recipe[: -len(".munki.recipe")]
        return f"local.munki.{product}", product
    if stem.startswith("local.munki."):
        return stem, stem[len("local.munki.") :]
    if stem.startswith("com."):
        return stem, stem.split(".")[-1]
    return f"local.munki.{stem}", stem


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers=_json_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), resp.status
    except Exception as e:
        print(f"  POST {url} failed: {e}")
        return None, 0


def munki_repo_root() -> str:
    """Directory where MunkiImporter / AutoPkg place ``pkgs``, ``pkgsinfo``, ``icons``.

    **Prefer AutoPkg's preference first** — MunkiImporter uses
    ``com.github.autopkg`` ``MUNKI_REPO``, which may differ from a shell
    ``export MUNKI_REPO=`` (e.g. clone root vs another repo the user set via
    ``defaults write``). The shell export was checked first before and could
    make us look in the wrong ``icons/`` for upload.
    """
    try:
        r = subprocess.run(
            ["defaults", "read", "com.github.autopkg", "MUNKI_REPO"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    e = os.environ.get("MUNKI_REPO", "").strip()
    if e:
        return e
    ws = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if ws:
        return ws
    return ""


def _resolve_pkg_abs_path(item: dict, pkginfo_dict: dict, mroot: str) -> str:
    """Best-effort absolute path to the pkg/dmg on disk.

    AutoPkg's MunkiImporter populates ``pkg_repo_path`` on the summary data
    row, but cloud-autopkg-runner sometimes strips that key. When it is
    missing, fall back to ``pkginfo.installer_item_location`` (relative to
    ``<MUNKI_REPO>/pkgs/``) since we just successfully ingested that pkginfo.
    Returns an empty string when no candidate path resolves to a real file
    so the caller can log a clear "couldn't find on disk" message.
    """
    if not mroot:
        return ""
    candidates: list[str] = []
    repo_rel = (item.get("pkg_repo_path") or "").strip()
    if repo_rel:
        candidates.append(os.path.join(mroot, repo_rel))
        # Some MunkiImporter outputs already include ``pkgs/`` in the rel path;
        # others give just ``apps/Foo.dmg``. Cover both shapes.
        if not repo_rel.startswith("pkgs" + os.sep) and not repo_rel.startswith("pkgs/"):
            candidates.append(os.path.join(mroot, "pkgs", repo_rel))
    iil = (pkginfo_dict.get("installer_item_location") or "").strip()
    if iil:
        candidates.append(os.path.join(mroot, "pkgs", iil))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def _post_multipart_upload_pkg(
    api_base: str,
    run_id: str,
    recipe_identifier: str,
    pkg_path: str,
    relative_path: str = "",
) -> str | None:
    """Stream a pkg/dmg into the backend storage uploader.

    ``relative_path`` (when set) tells the backend where to put the blob —
    typically ``pkgs/<installer_item_location>`` from the pkginfo. Passing
    this keeps the storage layout in lockstep with what Munki clients will
    download via ``installer_item_location``. When empty the backend falls
    back to its slug-based default (``pkgs/<recipe_slug>/<filename>``).

    Returns the public URL on success, ``None`` when the backend is unconfigured
    (HTTP 503) — the caller then falls back to path-only reporting so old
    deployments keep working.
    """
    if not pkg_path or not os.path.isfile(pkg_path):
        return None

    url = f"{api_base.rstrip('/')}/runs/{run_id}/pkgs"
    boundary = f"----AutomunkiPkg{uuid.uuid4().hex}"
    b = boundary.encode("ascii", errors="strict")
    eol = b"\r\n"

    try:
        with open(pkg_path, "rb") as f:
            pkg_bytes = f.read()
    except OSError as e:
        print(f"  Could not read pkg {pkg_path}: {e}")
        return None

    filename = os.path.basename(pkg_path).encode("utf-8", errors="replace")
    parts: list[bytes] = [
        b"--",
        b,
        eol,
        b'Content-Disposition: form-data; name="recipe_identifier"',
        eol,
        eol,
        recipe_identifier.encode("utf-8"),
        eol,
    ]
    if relative_path:
        parts.extend(
            [
                b"--",
                b,
                eol,
                b'Content-Disposition: form-data; name="relative_path"',
                eol,
                eol,
                relative_path.encode("utf-8"),
                eol,
            ]
        )
    parts.extend(
        [
            b"--",
            b,
            eol,
            b'Content-Disposition: form-data; name="file"; filename="',
            filename,
            b'"',
            eol,
            b"Content-Type: application/octet-stream",
            eol,
            eol,
            pkg_bytes,
            eol,
            b"--",
            b,
            b"--",
            eol,
        ]
    )
    body = b"".join(parts)
    h = _json_headers()
    h["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("imported_pkg_url")
    except urllib.error.HTTPError as e:
        # Read the body once so the message we print reflects what the server
        # actually said. The previous behavior treated *any* 503 as
        # "STORAGE_BACKEND=none", which masked Container Apps ingress 503s
        # (e.g. backend OOM-killed mid-upload of a large pkg) under a
        # misleading message.
        err_body = e.read().decode("utf-8", errors="replace")[:500]
        if e.code == 503 and "STORAGE_BACKEND=none" in err_body:
            print("  STORAGE_BACKEND=none on server; skipping pkg upload")
            return None
        print(f"  Pkg upload HTTP {e.code}: {err_body or '(no body)'}")
        return None
    except Exception as e:
        print(f"  Pkg upload failed: {e}")
        return None


def _post_multipart_ingest_icon(api_base: str, icon_stem: str, png_bytes: bytes) -> bool:
    """POST PNG to /autopkg/icons/ingest (multipart, same as UI upload)."""
    url = f"{api_base.rstrip('/')}/icons/ingest"
    boundary = f"----AutomunkiIcon{uuid.uuid4().hex}"
    b = boundary.encode("ascii", errors="strict")
    eol = b"\r\n"
    # Multipart: each header line must end with CRLF; blank line before part body.
    body = b"".join(
        [
            b"--",
            b,
            eol,
            b'Content-Disposition: form-data; name="icon_name"',
            eol,
            eol,
            icon_stem.encode("utf-8"),
            eol,
            b"--",
            b,
            eol,
            b'Content-Disposition: form-data; name="file"; filename="icon.png"',
            eol,
            b"Content-Type: image/png",
            eol,
            eol,
            png_bytes,
            eol,
            b"--",
            b,
            b"--",
            eol,
        ]
    )
    # Must not merge _json_headers() before setting Content-Type: it sets
    # application/json and would override multipart, yielding 422 "file" missing.
    h = _json_headers()
    h["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(
        url,
        data=body,
        headers=h,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if 200 <= resp.status < 300:
                return True
            err_body = resp.read().decode("utf-8", errors="replace")[:500]
            print(f"  Icon ingest HTTP {resp.status} for {icon_stem}: {err_body or '(no body)'}")
            return False
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:500]
        print(
            f"  POST {url} (icon) failed: {e!s} {err_body or ''}"
        )
        return False
    except Exception as e:
        print(f"  POST {url} (icon) failed: {e}")
        return False


def _icon_name_stem_candidates(item: dict, pkginfo_dict: dict) -> list[str]:
    """Stems to try for ``icons/<stem>.png`` (Munki default is often package ``name``)."""
    out: list[str] = []
    for raw in (
        pkginfo_dict.get("icon_name"),
        item.get("icon_repo_path"),
        item.get("name"),
        pkginfo_dict.get("name"),
    ):
        if not raw or not str(raw).strip():
            continue
        s = str(raw).strip()
        if s.lower().endswith(".png"):
            s = s[: -len(".png")]
        if "/" in s or "\\" in s:
            s = os.path.splitext(os.path.basename(s))[0]
        if s and s not in out:
            out.append(s)
    return out


def upload_extracted_icon_if_present(
    api_base: str, item: dict, pkginfo_dict: dict, pkgsinfo_dir: str
) -> None:
    mroot = munki_repo_root()
    if not mroot:
        print("  No MUNKI_REPO / GITHUB_WORKSPACE: skipping icon upload")
        return
    icons = os.path.join(mroot, "icons")
    icon_rel = (item.get("icon_repo_path") or "").strip()
    stems = _icon_name_stem_candidates(item, pkginfo_dict)

    paths_to_try: list[str] = []
    if icon_rel:
        paths_to_try.append(os.path.join(icons, icon_rel))
    for stem in stems:
        paths_to_try.append(os.path.join(icons, f"{stem}.png"))

    path = None
    for candidate in paths_to_try:
        if candidate and os.path.isfile(candidate):
            path = candidate
            break
    if not path:
        if paths_to_try:
            _tried = ", ".join(os.path.basename(p) for p in paths_to_try[:5])
            if len(paths_to_try) > 5:
                _tried += ", …"
            print(
                "  No icon PNG on disk for upload "
                f"(tried under {icons!r}: {_tried}). "
                "Enable 'Extract icon (MunkiImporter)' on the recipe in Munki Manager "
                "so Input.extract_icon is set (AutoPkg MunkiImporter only extracts when "
                "that key is true; the munkiimport CLI can prompt for icons separately)."
            )
        return

    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"  Could not read icon {path}: {e}")
        return
    if len(data) < 8 or data[:8] != b"\x89PNG\r\n\x1a\n":
        print("  Skipping non-PNG icon for upload")
        return
    from_pkg = (pkginfo_dict.get("icon_name") or "").strip()
    stem = from_pkg or os.path.splitext(os.path.basename(path))[0]
    if not stem:
        return
    if _post_multipart_ingest_icon(api_base, stem, data):
        print(f"  Ingested icon: {stem}.png")


def main():
    api_base = os.environ["API_BASE_URL"] + "/api/v1/autopkg"
    run_id = os.environ["RUN_ID"]
    report_path = os.environ.get("REPORT_FILE", "")
    # Same root as ``munki_repo_root()``: MunkiImporter writes here, not only under GITHUB_WORKSPACE.
    _root = munki_repo_root()
    pkgsinfo_dir = (
        os.path.join(_root, "pkgsinfo") if _root else os.environ.get("PKGSINFO_DIR", "")
    )

    if not report_path or not os.path.exists(report_path):
        print(f"Report not found: {report_path}")
        sys.exit(0)

    with open(report_path, "rb") as f:
        report = plistlib.load(f)

    failures = report.get("failures", [])
    summary = report.get("summary_results", {})
    munki_summary = summary.get("munki_importer_summary_result", {})
    imported_items = munki_summary.get("data_rows", [])

    identifier, recipe_name = recipe_identifier_and_name(report_path, report)
    duration_seconds = _duration_seconds_from_report(report)

    if imported_items:
        for item in imported_items:
            catalogs = item.get("catalogs", "")
            if isinstance(catalogs, str):
                catalogs = [
                    c.strip() for c in re.split(r"[,/|]+", catalogs) if c.strip()
                ]

            pkginfo_dict: dict = {}
            pkginfo_path = item.get("pkginfo_path", "")
            if pkginfo_path and pkgsinfo_dir:
                full_path = os.path.join(pkgsinfo_dir, pkginfo_path)
                if os.path.exists(full_path):
                    with open(full_path, "rb") as pf:
                        pkginfo_dict = plistlib.load(pf)
                    serializable = make_serializable(pkginfo_dict)
                    resp_body, ingest_status = post_json(
                        f"{api_base}/pkginfo/ingest",
                        {
                            "pkginfo": serializable,
                            "recipe_identifier": identifier,
                        },
                    )
                    if resp_body and isinstance(resp_body.get("catalog_names"), list):
                        catalogs = list(resp_body["catalog_names"])
                    if resp_body and resp_body.get("skipped"):
                        if resp_body.get("catalogs_synced"):
                            print(
                                f"  Synced catalogs from pkginfo plist: "
                                f"{item.get('name')} {item.get('version')}"
                            )
                        else:
                            print(
                                f"  Pkginfo already in DB: "
                                f"{item.get('name')} {item.get('version')}"
                            )
                    elif ingest_status == 200:
                        print(
                            f"  Ingested pkginfo: "
                            f"{item.get('name')} {item.get('version')}"
                        )
                    else:
                        print(f"  Pkginfo ingest response: {resp_body}")
                else:
                    print(f"  Pkginfo file not found at {full_path}")

            upload_extracted_icon_if_present(api_base, item, pkginfo_dict, pkgsinfo_dir)

            # Stream the pkg/dmg bytes to the backend's storage uploader. The
            # response is the public URL the storage backend wrote to (Azure
            # Blob/S3); we attach it to the run result so the UI / pkginfo
            # ingest can prefer it over MUNKI_REPO_PKG_BASE_URL.
            mroot_for_pkg = munki_repo_root()
            pkg_abs_path = _resolve_pkg_abs_path(item, pkginfo_dict, mroot_for_pkg)
            imported_pkg_url: str | None = None
            if pkg_abs_path:
                # Storage path mirrors ``installer_item_location`` from the
                # pkginfo so Munki clients can resolve the blob from the URL
                # they see in the pkginfo plist. We prefix ``pkgs/`` to match
                # the conventional Munki repo layout (``<repo>/pkgs/<iil>``).
                iil = (pkginfo_dict.get("installer_item_location") or "").strip().lstrip("/")
                relative_path = f"pkgs/{iil}" if iil else ""
                print(
                    f"  Uploading pkg: {os.path.basename(pkg_abs_path)} "
                    f"({os.path.getsize(pkg_abs_path)} bytes)"
                    + (f" -> {relative_path}" if relative_path else "")
                )
                imported_pkg_url = _post_multipart_upload_pkg(
                    api_base, run_id, identifier, pkg_abs_path,
                    relative_path=relative_path,
                )
                if imported_pkg_url:
                    print(f"  Uploaded pkg -> {imported_pkg_url}")
                # _post_multipart_upload_pkg already logs on 503 / HTTP errors.
            else:
                # Surface why we skipped so it's not silent. ``pkg_repo_path``
                # comes from MunkiImporter's summary data row;
                # ``installer_item_location`` from the pkginfo plist. If
                # neither yields a file on disk we can't upload.
                tried = []
                if (item.get("pkg_repo_path") or "").strip():
                    tried.append(f"pkg_repo_path={item['pkg_repo_path']!r}")
                if (pkginfo_dict.get("installer_item_location") or "").strip():
                    tried.append(
                        f"installer_item_location={pkginfo_dict['installer_item_location']!r}"
                    )
                tried_str = ", ".join(tried) if tried else "no path on report or pkginfo"
                print(
                    f"  Skipping pkg upload — no file found under "
                    f"MUNKI_REPO={mroot_for_pkg!r} ({tried_str})"
                )

            result_payload = {
                "recipe_identifier": identifier,
                "recipe_name": recipe_name,
                "status": "imported",
                "imported_version": item.get("version"),
                "imported_display_name": imported_display_title(
                    item, pkgsinfo_dir, recipe_name
                ),
                "imported_pkg_path": item.get("pkg_repo_path"),
                "imported_pkg_url": imported_pkg_url,
                "imported_pkginfo_path": item.get("pkginfo_path"),
                "imported_catalogs": catalogs,
            }
            if duration_seconds is not None:
                result_payload["duration_seconds"] = duration_seconds
            _, status = post_json(
                f"{api_base}/runs/{run_id}/results", result_payload
            )
            print(
                f"  Reported imported: {item.get('name')} "
                f"{item.get('version')} ({status})"
            )

    elif failures:
        error_msg = "; ".join(
            f.get("message", "") for f in failures if isinstance(f, dict)
        )
        failed_payload = {
            "recipe_identifier": identifier,
            "recipe_name": recipe_name,
            "status": "failed",
            "error_message": error_msg,
        }
        if duration_seconds is not None:
            failed_payload["duration_seconds"] = duration_seconds
        post_json(f"{api_base}/runs/{run_id}/results", failed_payload)
        print(f"  Reported failed: {recipe_name}")
    else:
        log_error = _failure_from_autopkg_runner_log(report_path)
        if log_error:
            failed_payload = {
                "recipe_identifier": identifier,
                "recipe_name": recipe_name,
                "status": "failed",
                "error_message": log_error,
            }
            if duration_seconds is not None:
                failed_payload["duration_seconds"] = duration_seconds
            post_json(f"{api_base}/runs/{run_id}/results", failed_payload)
            print(f"  Reported failed (from autopkg_runner.log): {recipe_name}")
        else:
            no_change_payload = {
                "recipe_identifier": identifier,
                "recipe_name": recipe_name,
                "status": "no_change",
            }
            if duration_seconds is not None:
                no_change_payload["duration_seconds"] = duration_seconds
            post_json(f"{api_base}/runs/{run_id}/results", no_change_payload)
            print(f"  Reported no_change: {recipe_name}")


if __name__ == "__main__":
    main()
