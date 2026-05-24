"""Enrollment token hashing, profile generation, and path RBAC mapping."""

from __future__ import annotations

import plistlib
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from automunki.core.page_keys import PageKey, api_path_to_page_key
from automunki.core.secret_box import decrypt_for, encrypt_for
from automunki.services import enrollment
from automunki.services.enrollment import (
    _SECRET_PURPOSE_BASIC_AUTH,
    _hash_token,
    build_profile,
    generate_token,
)


def test_generate_token_is_unique_and_urlsafe():
    a = generate_token()
    b = generate_token()
    assert a != b
    assert len(a) >= 20
    # token_urlsafe produces [A-Za-z0-9_-]
    import string

    allowed = set(string.ascii_letters + string.digits + "-_")
    assert set(a) <= allowed


def test_hash_is_stable():
    assert _hash_token("abc") == _hash_token("abc")
    assert _hash_token("abc") != _hash_token("abd")


def test_enroll_routes_map_to_admin_settings():
    assert api_path_to_page_key("/api/v1/enroll/tokens") == PageKey.admin_settings
    assert api_path_to_page_key("/api/v1/enroll/tokens/abc") == PageKey.admin_settings


# ---------------------------------------------------------------------------
# build_profile: plist shape
# ---------------------------------------------------------------------------


@dataclass
class _StubAuth:
    """Stand-in for ``ResolvedRepoBasicAuth``."""

    active: bool = False
    username: str = ""
    password_hash: str = ""
    env_plain_password: str | None = None
    env_override: bool = False
    # Keep the field list flexible in case new fields are added later.
    extra: dict = field(default_factory=dict)


def _managed_installs(profile_bytes: bytes) -> dict:
    """Extract the Munki prefs dict from a generated .mobileconfig.

    Modern profile layout: a single payload whose ``PayloadType`` is
    ``ManagedInstalls`` — the Munki keys sit at the top level of that
    payload alongside the ``Payload*`` metadata. Callers only care about
    the Munki keys, so strip the payload scaffolding first.
    """
    payload = plistlib.loads(profile_bytes)["PayloadContent"][0]
    assert payload["PayloadType"] == "ManagedInstalls"
    return {k: v for k, v in payload.items() if not k.startswith("Payload")}


@dataclass
class _StubRepoUrls:
    """Stand-in for ``ResolvedRepoUrls``."""

    package_url: str = ""
    client_resource_url: str = ""
    package_url_env_override: bool = False
    client_resource_url_env_override: bool = False
    client_resource_url_derived: bool = False


@pytest.fixture
def patch_server_url(monkeypatch):
    monkeypatch.setattr(enrollment.settings, "api_public_url", "https://munki.example.com", raising=False)

    # Default: no external PackageURL / ClientResourceURL configured.
    # Individual tests can override by re-patching `resolve_repo_urls`.
    async def _stub_resolve_urls(_session):
        return _StubRepoUrls()

    monkeypatch.setattr(enrollment, "resolve_repo_urls", _stub_resolve_urls)
    yield


async def test_build_profile_minimum_fields(patch_server_url, monkeypatch):
    async def _stub_resolve(_session):
        return _StubAuth(active=False)

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    out = await build_profile(session=None, manifest_name=None)
    profile = plistlib.loads(out)

    assert profile["PayloadType"] == "Configuration"
    assert profile["PayloadScope"] == "System"
    # Modern profile: the inner payload's PayloadType is "ManagedInstalls"
    # (no com.apple.ManagedClient.preferences wrapper, no Forced array).
    assert profile["PayloadContent"][0]["PayloadType"] == "ManagedInstalls"

    mi = _managed_installs(out)
    assert mi["SoftwareRepoURL"] == "https://munki.example.com/repo"
    assert "ClientIdentifier" not in mi
    assert "AdditionalHttpHeaders" not in mi
    assert "PackageURL" not in mi
    assert "ClientResourceURL" not in mi
    # We're not relying on redirects anymore; shouldn't force-enable this.
    assert "FollowHTTPRedirects" not in mi


async def test_build_profile_with_manifest(patch_server_url, monkeypatch):
    async def _stub_resolve(_session):
        return _StubAuth(active=False)

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    out = await build_profile(session=None, manifest_name="site_default")
    mi = _managed_installs(out)
    assert mi["ClientIdentifier"] == "site_default"


async def test_build_profile_embeds_env_basic_auth(patch_server_url, monkeypatch):
    async def _stub_resolve(_session):
        return _StubAuth(active=True, username="munki", env_plain_password="s3cret")

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    out = await build_profile(session=None, manifest_name=None)
    mi = _managed_installs(out)

    headers = mi["AdditionalHttpHeaders"]
    assert isinstance(headers, list) and len(headers) == 1
    assert headers[0].startswith("Authorization: Basic ")


async def test_build_profile_db_basic_auth_skips_header_without_token(patch_server_url, monkeypatch):
    """When only a hash is available and no token header is cached, no header."""

    async def _stub_resolve(_session):
        return _StubAuth(active=True, username="munki", password_hash="argon2$…")

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    out = await build_profile(session=None, manifest_name=None)
    mi = _managed_installs(out)
    assert "AdditionalHttpHeaders" not in mi


async def test_build_profile_uses_token_embedded_header_over_server(patch_server_url, monkeypatch):
    """DB-mode Basic auth: the token-cached header wins and is included."""

    async def _stub_resolve(_session):
        # Server only has the hash — by itself it couldn't embed a header.
        return _StubAuth(active=True, username="munki", password_hash="argon2$…")

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    header = "Authorization: Basic bXVua2k6czNjcmV0"
    token = SimpleNamespace(
        embedded_basic_auth_enc=encrypt_for(_SECRET_PURPOSE_BASIC_AUTH, header),
    )

    out = await build_profile(session=None, manifest_name=None, token=token)
    mi = _managed_installs(out)
    assert mi["AdditionalHttpHeaders"] == [header]


async def test_build_profile_includes_package_and_client_resource_urls(patch_server_url, monkeypatch):
    """PackageURL / ClientResourceURL are written through verbatim."""

    async def _stub_resolve(_session):
        return _StubAuth(active=False)

    async def _stub_resolve_urls(_session):
        return _StubRepoUrls(
            package_url="https://cdn.example.com/pkgs",
            client_resource_url="https://cdn.example.com/client_resources",
        )

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)
    monkeypatch.setattr(enrollment, "resolve_repo_urls", _stub_resolve_urls)

    out = await build_profile(session=None, manifest_name=None)
    mi = _managed_installs(out)

    assert mi["PackageURL"] == "https://cdn.example.com/pkgs"
    assert mi["ClientResourceURL"] == "https://cdn.example.com/client_resources"


async def test_build_profile_omits_url_prefs_when_unset(patch_server_url, monkeypatch):
    """Empty-string URLs from the resolver should not emit the preference at all."""

    async def _stub_resolve(_session):
        return _StubAuth(active=False)

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    out = await build_profile(session=None, manifest_name=None)
    mi = _managed_installs(out)
    assert "PackageURL" not in mi
    assert "ClientResourceURL" not in mi


async def test_secret_box_round_trip():
    ciphertext = encrypt_for(_SECRET_PURPOSE_BASIC_AUTH, "hello")
    assert ciphertext and ciphertext != "hello"
    assert decrypt_for(_SECRET_PURPOSE_BASIC_AUTH, ciphertext) == "hello"
    assert decrypt_for(_SECRET_PURPOSE_BASIC_AUTH, "not-a-fernet-token") is None
    # Different purpose → cannot decrypt
    assert decrypt_for("other.purpose", ciphertext) is None


async def test_build_profile_requires_server_url(monkeypatch):
    monkeypatch.setattr(enrollment.settings, "api_public_url", "", raising=False)
    monkeypatch.setattr(enrollment.settings, "public_app_url", "", raising=False)

    async def _stub_resolve(_session):
        return _StubAuth(active=False)

    monkeypatch.setattr(enrollment, "resolve_effective_auth", _stub_resolve)

    with pytest.raises(ValueError, match="Server base URL"):
        await build_profile(session=None, manifest_name=None)
