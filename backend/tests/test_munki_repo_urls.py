"""Tests for `services/munki_repo_urls.py`.

Covers:
- Pure URL-derivation (no DB, no env).
- Env overrides vs DB values precedence.
- Empty/"https://host" edge cases.
"""

from __future__ import annotations

import pytest

from automunki.services import munki_repo_urls as mru
from automunki.services.munki_repo_urls import (
    ResolvedRepoUrls,
    _derive_client_resource_url,
)

# ---------------------------------------------------------------------------
# Pure derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pkg, expected",
    [
        ("https://host.example.com/pkgs", "https://host.example.com/client_resources"),
        ("https://host.example.com/munki/pkgs", "https://host.example.com/munki/client_resources"),
        ("https://host.example.com/munki/pkgs/", "https://host.example.com/munki/client_resources"),
        ("https://host.example.com", ""),  # no path → can't invent one
        ("https://host.example.com/", ""),
        ("", ""),
        ("   ", ""),
    ],
)
def test_derive_client_resource_url(pkg, expected):
    assert _derive_client_resource_url(pkg) == expected


# ---------------------------------------------------------------------------
# resolve_repo_urls
# ---------------------------------------------------------------------------


class _StubRow:
    def __init__(self, pkg: str = "", cr: str = ""):
        self.package_url = pkg
        self.client_resource_url = cr


async def _patch_row(monkeypatch, row):
    async def _get(_session):
        return row

    monkeypatch.setattr(mru, "get_singleton_row", _get)


async def test_resolve_env_overrides_db(monkeypatch):
    monkeypatch.setattr(mru.settings, "munki_repo_pkg_base_url", "https://env.example.com/pkgs", raising=False)
    monkeypatch.setattr(
        mru.settings,
        "munki_repo_client_resources_base_url",
        "https://env.example.com/client_resources",
        raising=False,
    )
    await _patch_row(monkeypatch, _StubRow(pkg="https://db.example.com/pkgs", cr="https://db.example.com/cr"))

    out = await mru.resolve_repo_urls(session=None)
    assert isinstance(out, ResolvedRepoUrls)
    assert out.package_url == "https://env.example.com/pkgs"
    assert out.client_resource_url == "https://env.example.com/client_resources"
    assert out.package_url_env_override is True
    assert out.client_resource_url_env_override is True
    assert out.client_resource_url_derived is False


async def test_resolve_db_values_when_no_env(monkeypatch):
    monkeypatch.setattr(mru.settings, "munki_repo_pkg_base_url", "", raising=False)
    monkeypatch.setattr(mru.settings, "munki_repo_client_resources_base_url", "", raising=False)
    await _patch_row(
        monkeypatch,
        _StubRow(pkg="https://db.example.com/pkgs", cr="https://db.example.com/other_resources"),
    )

    out = await mru.resolve_repo_urls(session=None)
    assert out.package_url == "https://db.example.com/pkgs"
    assert out.client_resource_url == "https://db.example.com/other_resources"
    assert out.package_url_env_override is False
    assert out.client_resource_url_env_override is False
    assert out.client_resource_url_derived is False


async def test_resolve_derives_client_resource_url_when_only_pkg_set(monkeypatch):
    monkeypatch.setattr(mru.settings, "munki_repo_pkg_base_url", "", raising=False)
    monkeypatch.setattr(mru.settings, "munki_repo_client_resources_base_url", "", raising=False)
    await _patch_row(monkeypatch, _StubRow(pkg="https://db.example.com/pkgs", cr=""))

    out = await mru.resolve_repo_urls(session=None)
    assert out.package_url == "https://db.example.com/pkgs"
    assert out.client_resource_url == "https://db.example.com/client_resources"
    assert out.client_resource_url_derived is True


async def test_resolve_returns_empty_when_nothing_configured(monkeypatch):
    monkeypatch.setattr(mru.settings, "munki_repo_pkg_base_url", "", raising=False)
    monkeypatch.setattr(mru.settings, "munki_repo_client_resources_base_url", "", raising=False)
    await _patch_row(monkeypatch, None)

    out = await mru.resolve_repo_urls(session=None)
    assert out.package_url == ""
    assert out.client_resource_url == ""
    assert out.client_resource_url_derived is False


async def test_resolve_trims_trailing_slashes(monkeypatch):
    monkeypatch.setattr(mru.settings, "munki_repo_pkg_base_url", "https://env.example.com/pkgs/", raising=False)
    monkeypatch.setattr(mru.settings, "munki_repo_client_resources_base_url", "", raising=False)
    await _patch_row(monkeypatch, None)

    out = await mru.resolve_repo_urls(session=None)
    assert out.package_url == "https://env.example.com/pkgs"
    # Derivation happens off the already-trimmed value.
    assert out.client_resource_url == "https://env.example.com/client_resources"
    assert out.client_resource_url_derived is True
