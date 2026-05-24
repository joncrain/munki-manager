"""munkiimport-lite Linux-side extraction + storage routing."""

from __future__ import annotations

import hashlib
import io
import struct
import tempfile
import zlib
from collections.abc import AsyncIterator
from typing import ClassVar

import pytest

from automunki.services.munki_import import (
    _derive_name,
    _detect_kind,
    _parse_pkg_metadata,
    _safe_filename,
    _slug,
    build_import_plan,
    cleanup_temp,
    stream_upload_to_temp,
)

# ── Helpers to build a synthetic xar with a single PackageInfo entry. ─────────


def _build_minimal_xar(package_info_xml: bytes) -> bytes:
    """Construct a xar archive with one ``PackageInfo`` file (no signing).

    Layout: 28-byte header → zlib(toc XML) → file payloads.
    """
    pi_compressed = zlib.compress(package_info_xml)
    file_offset = 0
    file_length = len(pi_compressed)

    toc = (
        b"<?xml version='1.0' encoding='UTF-8'?>"
        b"<xar><toc><file id='1'>"
        b"<name>PackageInfo</name>"
        b"<type>file</type>"
        b"<data>"
        + f"<offset>{file_offset}</offset>".encode()
        + f"<length>{file_length}</length>".encode()
        + b"<encoding style='application/x-gzip'/>"
        b"</data></file></toc></xar>"
    )
    toc_compressed = zlib.compress(toc)
    header_size = 28
    version = 1
    cksum_alg = 0  # none
    header = (
        b"xar!"
        + struct.pack(">H", header_size)
        + struct.pack(">H", version)
        + struct.pack(">Q", len(toc_compressed))
        + struct.pack(">Q", len(toc))
        + struct.pack(">I", cksum_alg)
    )
    return header + toc_compressed + pi_compressed


def _write_temp(blob: bytes) -> str:
    fp = tempfile.NamedTemporaryFile(delete=False, suffix=".pkg")
    fp.write(blob)
    fp.flush()
    fp.close()
    return fp.name


# ── Detection & sanitization ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Firefox.pkg", "pkg"),
        ("Firefox.PKG", "pkg"),
        ("Office.mpkg", "pkg"),
        ("Firefox.dmg", "dmg"),
        ("README.txt", "unknown"),
    ],
)
def test_detect_kind(name: str, expected: str) -> None:
    assert _detect_kind(name) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Firefox", "Firefox"),
        ("Firefox 130", "Firefox_130"),
        ("../etc/passwd", "etc_passwd"),
        ("", "uploaded"),
    ],
)
def test_slug(raw: str, expected: str) -> None:
    assert _slug(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Firefox.pkg", "Firefox.pkg"),
        ("/path/with/dirs/Firefox.pkg", "Firefox.pkg"),
        ("Spaced Name.pkg", "Spaced_Name.pkg"),
        ("", "upload.bin"),
    ],
)
def test_safe_filename(raw: str, expected: str) -> None:
    assert _safe_filename(raw) == expected


# ── XAR/PackageInfo extraction ──────────────────────────────────────────────


def test_parse_pkg_metadata_extracts_version_and_receipts() -> None:
    pi = b'<?xml version="1.0" encoding="UTF-8"?><pkg-info identifier="org.mozilla.firefox" version="130.0"></pkg-info>'
    blob = _build_minimal_xar(pi)
    path = _write_temp(blob)
    try:
        meta, fully = _parse_pkg_metadata(path)
        assert fully is True
        assert meta["version"] == "130.0"
        assert meta["receipts"] == [{"packageid": "org.mozilla.firefox", "version": "130.0"}]
    finally:
        cleanup_temp(path)


def test_parse_pkg_metadata_unknown_format_returns_pending() -> None:
    """Random bytes must not trip the parser."""
    path = _write_temp(b"not a xar archive at all")
    try:
        meta, fully = _parse_pkg_metadata(path)
        assert fully is False
        assert meta["receipts"] == []
    finally:
        cleanup_temp(path)


# ── Streaming upload to temp (hash + size) ─────────────────────────────────


@pytest.mark.asyncio
async def test_stream_upload_to_temp_computes_hash() -> None:
    payload = b"first chunk " + b"second chunk " + b"third chunk"

    async def _gen() -> AsyncIterator[bytes]:
        yield b"first chunk "
        yield b"second chunk "
        yield b"third chunk"

    path, size, sha = await stream_upload_to_temp(_gen())
    try:
        assert size == len(payload)
        assert sha == hashlib.sha256(payload).hexdigest()
        with open(path, "rb") as fp:
            assert fp.read() == payload
    finally:
        cleanup_temp(path)


# ── End-to-end build_import_plan with a fake storage backend ───────────────


class _FakeStorage:
    name: ClassVar[str] = "fake"

    def __init__(self) -> None:
        self.uploaded_path = ""
        self.uploaded_bytes = b""

    async def upload(
        self,
        *,
        relative_path: str,
        body: AsyncIterator[bytes],
        content_length: int | None,
        content_type: str = "application/octet-stream",
    ) -> str:
        self.uploaded_path = relative_path
        buf = io.BytesIO()
        async for chunk in body:
            buf.write(chunk)
        self.uploaded_bytes = buf.getvalue()
        return f"https://example.test/{relative_path}"

    async def invalidate_cdn(self, paths: list[str]) -> None:
        return None


@pytest.mark.asyncio
async def test_build_import_plan_pkg_happy_path() -> None:
    pi = b'<?xml version="1.0" encoding="UTF-8"?><pkg-info identifier="com.acme.foo" version="2.5"></pkg-info>'
    blob = _build_minimal_xar(pi)
    path = _write_temp(blob)
    sha = hashlib.sha256(blob).hexdigest()
    storage = _FakeStorage()
    try:
        plan = await build_import_plan(
            temp_path=path,
            original_filename="Acme Foo 2.5.pkg",
            sha256_hex=sha,
            size_bytes=len(blob),
            name=None,
            display_name="Acme Foo",
            catalogs=["testing"],
            category="Utilities",
            developer="Acme",
            description=None,
            unattended_install=True,
            storage=storage,
        )
    finally:
        cleanup_temp(path)
    assert plan.version == "2.5"
    assert plan.name == "Acme_Foo"
    assert plan.display_name == "Acme Foo"
    assert plan.category == "Utilities"
    assert plan.unattended_install is True
    assert plan.installer_item_hash == sha
    assert plan.installer_item_size_kb == max(1, (len(blob) + 1023) // 1024)
    # Default storage layout: ``pkgs/<filename>`` (root of ``pkgs/``).
    # ``installer_item_location`` is the path *relative to* ``pkgs/`` so Munki
    # clients prepend ``MUNKI_REPO_PKG_BASE_URL`` — same shape as
    # AutoPkg-generated pkginfo plists.
    assert storage.uploaded_path == "pkgs/Acme_Foo_2.5.pkg"
    assert plan.installer_item_location == "Acme_Foo_2.5.pkg"
    assert plan.pending_metadata is False
    assert plan.receipts == [{"packageid": "com.acme.foo", "version": "2.5"}]


@pytest.mark.asyncio
async def test_build_import_plan_dmg_falls_back_to_pending() -> None:
    blob = b"\x00\x00\x00\x00fake dmg blob"
    path = _write_temp(blob)
    sha = hashlib.sha256(blob).hexdigest()
    storage = _FakeStorage()
    try:
        plan = await build_import_plan(
            temp_path=path,
            original_filename="Slack.dmg",
            sha256_hex=sha,
            size_bytes=len(blob),
            name=None,
            display_name="Slack",
            catalogs=[],
            category=None,
            developer=None,
            description=None,
            unattended_install=False,
            storage=storage,
        )
    finally:
        cleanup_temp(path)
    assert plan.pending_metadata is True
    assert plan.installer_type == ""  # drag-install convention
    # When no catalogs are supplied, defaults to "testing".
    assert plan.catalog_names == ["testing"]
    assert storage.uploaded_path == "pkgs/Slack.dmg"
    assert plan.installer_item_location == "Slack.dmg"


@pytest.mark.asyncio
async def test_build_import_plan_propagates_storage_not_configured() -> None:
    """When STORAGE_BACKEND=none, the noop backend raises and the route returns 503."""
    from automunki.core.config import settings
    from automunki.services.storage import (
        get_storage_backend,
        reset_storage_backend,
    )
    from automunki.services.storage.base import StorageNotConfiguredError

    blob = b"\x00" * 16
    path = _write_temp(blob)
    sha = hashlib.sha256(blob).hexdigest()

    original = settings.storage_backend
    try:
        settings.storage_backend = "none"
        reset_storage_backend()
        storage = get_storage_backend()
        with pytest.raises(StorageNotConfiguredError):
            await build_import_plan(
                temp_path=path,
                original_filename="x.dmg",
                sha256_hex=sha,
                size_bytes=len(blob),
                name=None,
                display_name="X",
                catalogs=["testing"],
                category=None,
                developer=None,
                description=None,
                unattended_install=False,
                storage=storage,
            )
    finally:
        settings.storage_backend = original
        reset_storage_backend()
        cleanup_temp(path)


@pytest.mark.asyncio
async def test_build_import_plan_unknown_extension_pending_metadata() -> None:
    blob = b"\x00" * 1024
    path = _write_temp(blob)
    sha = hashlib.sha256(blob).hexdigest()
    storage = _FakeStorage()
    try:
        plan = await build_import_plan(
            temp_path=path,
            original_filename="weird.bin",
            sha256_hex=sha,
            size_bytes=len(blob),
            name="weird-installer",
            display_name="Weird Installer",
            catalogs=["testing"],
            category=None,
            developer=None,
            description=None,
            unattended_install=False,
            storage=storage,
        )
    finally:
        cleanup_temp(path)
    assert plan.pending_metadata is True
    assert plan.name == "weird-installer"


# ── ``munki_repo_subdir`` placement ────────────────────────────────────────


async def _run_plan_with_subdir(subdir: str | None) -> tuple[_FakeStorage, object]:
    """Run a happy-path ``build_import_plan`` with the given ``munki_repo_subdir``."""
    pi = b'<?xml version="1.0" encoding="UTF-8"?><pkg-info identifier="com.acme.foo" version="3.0"></pkg-info>'
    blob = _build_minimal_xar(pi)
    path = _write_temp(blob)
    sha = hashlib.sha256(blob).hexdigest()
    storage = _FakeStorage()
    try:
        plan = await build_import_plan(
            temp_path=path,
            original_filename="Foo.pkg",
            sha256_hex=sha,
            size_bytes=len(blob),
            name=None,
            display_name="Foo",
            catalogs=["testing"],
            category=None,
            developer=None,
            description=None,
            unattended_install=False,
            storage=storage,
            munki_repo_subdir=subdir,
        )
    finally:
        cleanup_temp(path)
    return storage, plan


@pytest.mark.asyncio
async def test_build_import_plan_honors_munki_repo_subdir() -> None:
    storage, plan = await _run_plan_with_subdir("apps/Slack")
    assert storage.uploaded_path == "pkgs/apps/Slack/Foo.pkg"
    assert plan.installer_item_location == "apps/Slack/Foo.pkg"


@pytest.mark.asyncio
async def test_build_import_plan_strips_leading_pkgs_in_subdir() -> None:
    # Operators commonly paste paths that include the ``pkgs/`` prefix; we
    # tolerate it so the final storage path stays a single ``pkgs/...``.
    storage, plan = await _run_plan_with_subdir("pkgs/apps/Slack")
    assert storage.uploaded_path == "pkgs/apps/Slack/Foo.pkg"
    assert plan.installer_item_location == "apps/Slack/Foo.pkg"


@pytest.mark.asyncio
async def test_build_import_plan_treats_blank_subdir_as_root() -> None:
    storage, plan = await _run_plan_with_subdir("   ")
    assert storage.uploaded_path == "pkgs/Foo.pkg"
    assert plan.installer_item_location == "Foo.pkg"


@pytest.mark.asyncio
async def test_build_import_plan_strips_surrounding_slashes_in_subdir() -> None:
    storage, plan = await _run_plan_with_subdir("/apps/Slack/")
    assert storage.uploaded_path == "pkgs/apps/Slack/Foo.pkg"
    assert plan.installer_item_location == "apps/Slack/Foo.pkg"


@pytest.mark.asyncio
async def test_build_import_plan_rejects_path_traversal_subdir() -> None:
    # ``sanitize_relative_path`` is the canonical guard; surface its error
    # so the route can translate it to a 422.
    with pytest.raises(ValueError):
        await _run_plan_with_subdir("apps/../../etc")


# ── ``_derive_name`` ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label,name,display_name,filename,parsed_version,expected",
    [
        # Explicit override always wins, no stripping.
        (
            "explicit name with version-like suffix is preserved verbatim",
            "custom-1.2.3",
            "Anything",
            "anything.pkg",
            "1.2.3",
            "custom-1.2.3",
        ),
        # The original bug: filename stem leaks a ``-1.0.unsigned`` suffix
        # into ``name``. We expect both the heuristic and the exact-version
        # strip to peel it back to a Munki-resolvable base name.
        (
            "filename stem with -version suffix gets stripped",
            None,
            "munki-manager-client",
            "munki-manager-client-1.0.unsigned.pkg",
            "1.0",
            "munki-manager-client",
        ),
        # display_name preference: user typed a clean name, ignore filename.
        (
            "display_name wins over filename when both have version-y tails",
            None,
            "Slack",
            "Slack-4.36.0.pkg",
            "4.36.0",
            "Slack",
        ),
        # Heuristic strip for ``_<digit>...`` (slug converts spaces to ``_``).
        (
            "underscore-version tail (from spaces) is stripped",
            None,
            "Slack 4.36",
            "Slack 4.36.pkg",
            None,
            "Slack",
        ),
        # Heuristic strip for ``-<digit>...``.
        (
            "dash-version tail is stripped without parsed version",
            None,
            "Foo-2.0",
            "Foo-2.0.pkg",
            None,
            "Foo",
        ),
        # Non-digit dash segments must be left alone (e.g. company-product
        # names without an embedded version).
        (
            "non-version dash segments are preserved",
            None,
            "munki-manager-client",
            "munki-manager-client.pkg",
            None,
            "munki-manager-client",
        ),
        # Adjacent digits without a separator (Office2008 etc.) aren't a
        # version split. Munki treats these as part of the name; we do too.
        (
            "adjacent digits without separator are not stripped",
            None,
            "Office2008",
            "Office2008.pkg",
            None,
            "Office2008",
        ),
        # Blank display_name falls back to filename stem (with extension
        # stripped before slugging).
        (
            "blank display_name falls back to filename stem",
            None,
            "",
            "Firefox 130.0.pkg",
            "130.0",
            "Firefox",
        ),
        # Parsed-version suffix only matches when it exactly equals the tail;
        # mismatched values fall through to the heuristic.
        (
            "parsed version mismatch falls through to heuristic",
            None,
            "App_3.1.4",
            "App_3.1.4.pkg",
            "9.9.9",
            "App",
        ),
        # Pathological empty inputs still produce a usable name.
        (
            "empty everywhere falls back to uploaded",
            None,
            "",
            "",
            None,
            "uploaded",
        ),
    ],
)
def test_derive_name(
    label: str,
    name: str | None,
    display_name: str,
    filename: str,
    parsed_version: str | None,
    expected: str,
) -> None:
    """Ensure stored ``PkgInfo.name`` can't leak version-y content."""
    safe = _safe_filename(filename) if filename else ""
    result = _derive_name(
        name=name,
        display_name=display_name,
        safe_filename=safe,
        parsed_version=parsed_version,
    )
    assert result == expected, label


# ── End-to-end regression: the broken upload from the conversation ─────────


@pytest.mark.asyncio
async def test_build_import_plan_strips_version_from_filename_stem() -> None:
    """Reproduce the ``munki-manager-client-1.0.unsigned.pkg`` upload.

    Before the fix, leaving the "Name" field blank gave
    ``name = "munki-manager-client-1.0.unsigned"`` which Munki's
    ``nameAndVersion`` parser on the client would split into
    ``("munki-manager-client", "1.0.unsigned")`` — failing to resolve since
    no pkginfo with the trimmed base name existed.
    """
    pi = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<pkg-info identifier="com.example.munki-manager-client" '
        b'version="1.0"></pkg-info>'
    )
    blob = _build_minimal_xar(pi)
    path = _write_temp(blob)
    sha = hashlib.sha256(blob).hexdigest()
    storage = _FakeStorage()
    try:
        plan = await build_import_plan(
            temp_path=path,
            original_filename="munki-manager-client-1.0.unsigned.pkg",
            sha256_hex=sha,
            size_bytes=len(blob),
            name=None,
            display_name="munki-manager-client",
            catalogs=["testing"],
            category=None,
            developer=None,
            description=None,
            unattended_install=False,
            storage=storage,
        )
    finally:
        cleanup_temp(path)
    assert plan.name == "munki-manager-client"
    assert plan.version == "1.0"
    # Storage path still uses the filename verbatim so the binary lives
    # next to its versioned siblings; only ``name`` is the
    # manifest-facing identifier.
    assert storage.uploaded_path == "pkgs/munki-manager-client-1.0.unsigned.pkg"
    assert plan.installer_item_location == "munki-manager-client-1.0.unsigned.pkg"
