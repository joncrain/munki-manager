"""Linux-side ``munkiimport``-equivalent for the direct-upload route.

``munkiimport`` is a macOS-only Python tool from the munki-tools repo. The
backend container runs Linux, so we re-implement just the steps we need to
ingest a binary uploaded by an admin via the UI:

1. Stream the upload to a temp file (memory-bounded with ``SpooledTemporaryFile``).
2. Compute the hash + size Munki clients use.
3. Best-effort metadata extraction:
   - ``.pkg`` flat packages are xar archives; we list the table-of-contents
     directly without an external xar binary, then read ``PackageInfo`` /
     ``Distribution`` XML to populate ``receipts`` and ``version``.
   - ``.dmg`` extraction needs ``hdiutil``; on Linux we fall back to a
     ``pending_metadata`` pkginfo so the admin can fill in the rest in the UI.
4. Upload the bytes to the configured storage backend (Azure Blob / S3) under
   ``pkgs/`` — mirroring AutoPkg's repo layout. An optional
   ``munki_repo_subdir`` (e.g. ``apps/Slack``) nests the file further; the
   default is the root of ``pkgs/``.
5. Return a dict the route handler can persist as a ``PkgInfo`` row. The
   ``installer_item_location`` is the path *relative to* ``pkgs/`` (matching
   what AutoPkg's MunkiImporter writes and what Munki clients expect when
   they prepend ``MUNKI_REPO_PKG_BASE_URL``).

If the storage backend is ``none`` (default), the caller should surface a 503
instead of inserting a pkginfo row pointing at nowhere.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
import zlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import BinaryIO

import structlog

from automunki.services.storage import (
    StorageBackend,
    sanitize_relative_path,
)

logger = structlog.get_logger()

_SPOOL_MAX = 64 * 1024 * 1024  # 64 MiB in memory before spilling to disk
_READ_CHUNK = 1024 * 1024


@dataclass
class ImportPlan:
    """Result of running munkiimport-lite against a temp file."""

    name: str
    display_name: str
    version: str
    description: str | None
    developer: str | None
    category: str | None
    catalog_names: list[str]
    unattended_install: bool
    installer_item_location: str
    installer_item_hash: str
    installer_item_size_kb: int
    installer_type: str | None
    receipts: list[dict] | None = None
    minimum_os_version: str | None = None
    supported_architectures: list[str] | None = None
    pending_metadata: bool = False
    extra_metadata: dict = field(default_factory=dict)


def _slug(s: str) -> str:
    """Filesystem/blob-safe slug used as a fallback ``name`` for the pkginfo."""
    cleaned = re.sub(r"[^\w.\-]+", "_", s.strip(), flags=re.UNICODE).strip("._-")
    return cleaned or "uploaded"


def _safe_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE).strip("._-")
    return cleaned or "upload.bin"


_INSTALLER_EXT_RE = re.compile(r"\.(pkg|mpkg|dmg|zip)$", re.IGNORECASE)
# Mirrors Munki's ``nameAndVersion`` split (first ``-`` followed by a digit),
# extended to also accept ``_`` because our slug step converts whitespace to
# underscores: ``"Slack 4.36"`` slugs to ``"Slack_4.36"``, and we still want
# to peel the ``_4.36`` off so the stored ``PkgInfo.name`` is ``"Slack"``. We
# use this to strip a version-looking tail off an auto-derived ``name`` so
# the stored value doesn't collide with how Munki itself parses
# ``managed_installs`` entries on the client.
_VERSION_TAIL_RE = re.compile(r"[-_]\d[\w.\-]*$")


def _strip_installer_extension(filename: str) -> str:
    """Drop a single trailing ``.pkg`` / ``.mpkg`` / ``.dmg`` / ``.zip``."""
    return _INSTALLER_EXT_RE.sub("", filename)


def _derive_name(
    *,
    name: str | None,
    display_name: str,
    safe_filename: str,
    parsed_version: str | None,
) -> str:
    """Resolve the pkginfo ``name`` for a manually-uploaded binary.

    Rules, in order:

    1. An explicit ``name`` from the form always wins.
    2. Otherwise we slug the user-provided ``display_name``, falling back to
       the filename stem. ``display_name`` is preferred because the user
       typed it and almost always omits version-y content (whereas the file
       on disk routinely embeds the version, e.g. ``Slack-4.36.pkg``).
    3. If the binary's parsed version is a suffix of the slug (e.g. slug
       ``Slack_4.36`` and parsed version ``4.36``), drop that suffix. This
       is the most accurate version-strip — it only triggers when we *know*
       what the version is.
    4. As a safety net, strip a trailing ``-<digit>...`` segment. Munki's
       own ``nameAndVersion`` parser on the client splits manifest entries
       the same way; if our stored ``name`` ended in ``-<digit>...``, the
       client would split it off and look for a pkginfo that doesn't exist
       (which is exactly the regression that motivated this helper).
    5. Empty result falls back to ``_slug(safe_filename)`` or ``"uploaded"``.
    """
    if name and name.strip():
        return name.strip()

    source = (
        display_name.strip() if display_name and display_name.strip() else _strip_installer_extension(safe_filename)
    )
    base_slug = _slug(source)

    if parsed_version:
        v_slug = _slug(parsed_version)
        if v_slug and base_slug.lower().endswith(f"-{v_slug.lower()}"):
            base_slug = base_slug[: -(len(v_slug) + 1)].rstrip("._-")
        elif v_slug and base_slug.lower().endswith(f"_{v_slug.lower()}"):
            base_slug = base_slug[: -(len(v_slug) + 1)].rstrip("._-")

    tail = _VERSION_TAIL_RE.search(base_slug)
    if tail:
        trimmed = base_slug[: tail.start()].rstrip("._-")
        if trimmed:
            base_slug = trimmed

    return base_slug or _slug(safe_filename) or "uploaded"


def _normalize_repo_subdir(raw: str | None) -> str:
    """Clean a user-supplied ``MUNKI_REPO_SUBDIR`` form value.

    Returns ``""`` for missing / blank input. Strips leading/trailing slashes,
    collapses repeats, and tolerates the user typing ``pkgs/apps/Foo``
    (we drop the redundant ``pkgs/`` prefix so the final storage path stays
    a single ``pkgs/...``). Path traversal (``..``) and ``\\x00`` are caught
    downstream by ``sanitize_relative_path`` when we build the final path.
    """
    if not raw:
        return ""
    s = raw.strip().strip("/")
    if not s:
        return ""
    parts = [p for p in s.split("/") if p]
    if parts and parts[0] == "pkgs":
        parts = parts[1:]
    return "/".join(parts)


def _detect_kind(filename: str) -> str:
    """Return ``pkg``, ``dmg``, or ``unknown`` based on the trailing extension."""
    lower = filename.lower()
    if lower.endswith(".pkg") or lower.endswith(".mpkg"):
        return "pkg"
    if lower.endswith(".dmg"):
        return "dmg"
    return "unknown"


# ── xar parser (just enough to read the TOC + named files) ───────────────────


def _read_xar_toc(fp: BinaryIO) -> tuple[ET.Element, int] | None:
    """Parse the xar header + zlib-compressed TOC XML.

    Reference: https://github.com/mackyle/xar/wiki/xarformat — header is 28
    bytes (magic ``xar!``, header_size, version, toc_compressed_size,
    toc_uncompressed_size, cksum_alg). The TOC XML follows, then the heap
    (file payloads) — heap offsets in the TOC are relative to the start of
    the heap, not the start of the file. The returned ``int`` is the absolute
    file position where the heap begins (``header_size + toc_compressed_size``).
    """
    try:
        fp.seek(0)
        header = fp.read(28)
        if len(header) < 28 or header[:4] != b"xar!":
            return None
        header_size = struct.unpack(">H", header[4:6])[0]
        toc_comp_size = struct.unpack(">Q", header[8:16])[0]
        if header_size < 28:
            return None
        fp.seek(header_size)
        comp = fp.read(toc_comp_size)
        if not comp:
            return None
        try:
            xml_bytes = zlib.decompress(comp)
        except zlib.error:
            return None
        heap_start = header_size + toc_comp_size
        return ET.fromstring(xml_bytes), heap_start
    except (OSError, ET.ParseError):
        return None


def _toc_files(root: ET.Element) -> list[ET.Element]:
    """All ``<file>`` entries that have a ``data`` child (i.e. carry bytes)."""
    return [f for f in root.iter("file") if f.find("data") is not None]


def _file_name(elem: ET.Element) -> str:
    n = elem.find("name")
    return n.text if n is not None and n.text else ""


def _read_toc_file_bytes(fp: BinaryIO, heap_start: int, file_elem: ET.Element) -> bytes | None:
    data = file_elem.find("data")
    if data is None:
        return None

    def _child_text(name: str) -> str:
        # Element truthiness in xml.etree is based on having children, not on
        # the element existing — use ``is None`` checks explicitly.
        el = data.find(name)
        if el is None or el.text is None:
            return ""
        return el.text

    enc_el = data.find("encoding")
    encoding = enc_el.get("style", "") if enc_el is not None else ""
    try:
        offset = int(_child_text("offset") or "0")
        length = int(_child_text("length") or "0")
    except (TypeError, ValueError):
        return None
    if length <= 0:
        return None
    fp.seek(heap_start + offset)
    raw = fp.read(length)
    if "gzip" in encoding or "zlib" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return None
    if encoding and "octet-stream" not in encoding:
        # bzip2/lzma streams aren't worth pulling extra deps for; fall back to
        # pending_metadata when we hit one.
        return None
    return raw


def _parse_pkg_metadata(temp_path: str) -> tuple[dict, bool]:
    """Return ``(pkginfo_partial, fully_parsed)`` from a flat ``.pkg``.

    ``fully_parsed`` is False when the xar layout is unfamiliar (bundle-style
    .mpkg with sub-packages, payloads we couldn't decompress, etc.) — the
    caller flags ``pending_metadata`` in that case.
    """
    out: dict = {
        "version": "",
        "receipts": [],
        "minimum_os_version": "",
    }
    with open(temp_path, "rb") as fp:
        parsed = _read_xar_toc(fp)
        if parsed is None:
            return out, False
        toc, heap_start = parsed

        # Look for ``Distribution`` (top-level for .mpkg/.pkg) and
        # per-component ``PackageInfo`` files.
        dist_xml: bytes | None = None
        package_infos: list[bytes] = []
        for elem in _toc_files(toc):
            name = _file_name(elem)
            if name == "Distribution":
                dist_xml = _read_toc_file_bytes(fp, heap_start, elem)
            elif name == "PackageInfo":
                pi = _read_toc_file_bytes(fp, heap_start, elem)
                if pi:
                    package_infos.append(pi)

        # Receipts come from PackageInfo entries (one per sub-package).
        for pi in package_infos:
            try:
                pi_root = ET.fromstring(pi)
            except ET.ParseError:
                continue
            ident = pi_root.get("identifier") or ""
            ver = pi_root.get("version") or ""
            if ident:
                out["receipts"].append({"packageid": ident, "version": ver or ""})
                if not out["version"] and ver:
                    out["version"] = ver

        # Fall back to ``Distribution`` when we have no PackageInfo (e.g.
        # productbuild-style .pkg without flat sub-payloads).
        if dist_xml is not None and not out["receipts"]:
            try:
                d_root = ET.fromstring(dist_xml)
            except ET.ParseError:
                d_root = None
            if d_root is not None:
                for pkg_ref in d_root.iter("pkg-ref"):
                    ident = pkg_ref.get("id") or ""
                    ver = pkg_ref.get("version") or ""
                    if ident and ver:
                        out["receipts"].append({"packageid": ident, "version": ver})
                        if not out["version"]:
                            out["version"] = ver
                if not out["version"]:
                    title = d_root.find("title")
                    if title is not None and title.text:
                        out.setdefault("display_name", title.text.strip())

        # ``allowed-os-versions`` style ``<options hostArchitectures>`` etc. is
        # too rare to be worth parsing; leave ``minimum_os_version`` empty so
        # the admin can fill it in.

        fully = bool(out["version"]) or bool(out["receipts"])
    return out, fully


# ── Main entry point ─────────────────────────────────────────────────────────


async def stream_upload_to_temp(
    body: AsyncIterator[bytes],
) -> tuple[str, int, str]:
    """Drain an async upload body to a temp file. Returns ``(path, size, sha256)``."""
    spool = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
    sha = hashlib.sha256()
    size = 0
    try:
        async for chunk in body:
            if not chunk:
                continue
            spool.write(chunk)
            sha.update(chunk)
            size += len(chunk)
        spool.flush()
    finally:
        spool.close()
    return spool.name, size, sha.hexdigest()


async def build_import_plan(
    *,
    temp_path: str,
    original_filename: str,
    sha256_hex: str,
    size_bytes: int,
    name: str | None,
    display_name: str,
    catalogs: list[str],
    category: str | None,
    developer: str | None,
    description: str | None,
    unattended_install: bool,
    storage: StorageBackend,
    munki_repo_subdir: str | None = None,
) -> ImportPlan:
    """Run extraction + storage upload, return the plan to persist.

    ``munki_repo_subdir`` is the path under ``pkgs/`` where the binary should
    live (e.g. ``apps/Slack``). When empty/None, the file is uploaded directly
    under ``pkgs/<filename>``. The ``installer_item_location`` on the returned
    plan is the same path *relative to* ``pkgs/`` so Munki clients can resolve
    it against ``MUNKI_REPO_PKG_BASE_URL`` (matching what AutoPkg-generated
    pkginfo plists look like).
    """
    safe_filename = _safe_filename(original_filename)
    kind = _detect_kind(safe_filename)

    # Parse metadata first so the name-derivation step can use the version to
    # strip an exact suffix off the slug (see ``_derive_name``). For dmg /
    # unknown kinds we have no parsed version, so the helper falls back to
    # its ``-<digit>...`` heuristic.
    parsed_meta: dict = {}
    fully_parsed = False
    if kind == "pkg":
        parsed_meta, fully_parsed = _parse_pkg_metadata(temp_path)

    parsed_version = parsed_meta.get("version")
    name_value = _derive_name(
        name=name,
        display_name=display_name,
        safe_filename=safe_filename,
        parsed_version=str(parsed_version) if parsed_version else None,
    )

    plan_kwargs: dict = {
        "name": name_value,
        "display_name": display_name.strip() or name_value,
        "version": str(parsed_version) if parsed_version else "1.0",
        "description": description.strip() if description else None,
        "developer": developer.strip() if developer else None,
        "category": category.strip() if category else None,
        "catalog_names": [c.strip() for c in catalogs if c.strip()] or ["testing"],
        "unattended_install": bool(unattended_install),
        "installer_item_hash": sha256_hex,
        "installer_item_size_kb": max(1, (size_bytes + 1023) // 1024),
        "installer_type": None,
        "pending_metadata": False,
    }

    if kind == "pkg":
        if parsed_meta.get("receipts"):
            plan_kwargs["receipts"] = list(parsed_meta["receipts"])
        if parsed_meta.get("minimum_os_version"):
            plan_kwargs["minimum_os_version"] = str(parsed_meta["minimum_os_version"])
        plan_kwargs["installer_type"] = None  # default = pkg
        plan_kwargs["pending_metadata"] = not fully_parsed
    elif kind == "dmg":
        plan_kwargs["pending_metadata"] = True
        plan_kwargs["installer_type"] = ""  # MunkiAdmin convention for drag-install
    else:
        plan_kwargs["pending_metadata"] = True

    subdir = _normalize_repo_subdir(munki_repo_subdir)
    item_location = f"{subdir}/{safe_filename}" if subdir else safe_filename
    rel = sanitize_relative_path(f"pkgs/{item_location}")

    async def _file_iter() -> AsyncIterator[bytes]:
        with open(temp_path, "rb") as fp:
            while True:
                chunk = fp.read(_READ_CHUNK)
                if not chunk:
                    break
                yield chunk

    await storage.upload(
        relative_path=rel,
        body=_file_iter(),
        content_length=size_bytes,
        content_type="application/octet-stream",
    )
    plan_kwargs["installer_item_location"] = item_location
    return ImportPlan(**plan_kwargs)


def cleanup_temp(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
