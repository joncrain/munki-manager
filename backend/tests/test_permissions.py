"""RBAC permission helpers."""

from automunki.core.page_keys import PageKey, api_path_to_page_key
from automunki.services.permissions import can_access


def test_api_path_to_page_key_pkginfo():
    assert api_path_to_page_key("/api/v1/pkginfo") == PageKey.munki_software
    assert api_path_to_page_key("/api/v1/pkginfo/promotion-queue") == PageKey.munki_software


def test_api_path_to_page_key_auth_me_none():
    assert api_path_to_page_key("/api/v1/auth/me") is None


def test_api_path_to_page_key_auth_config_none():
    assert api_path_to_page_key("/api/v1/auth/config") is None


def test_can_access_write_implies_read():
    pk = PageKey.overview.value
    assert can_access({pk: "write"}, pk, need_write=True) is True
    assert can_access({pk: "write"}, pk, need_write=False) is True


def test_can_access_read_blocks_write():
    pk = PageKey.overview.value
    assert can_access({pk: "read"}, pk, need_write=True) is False
    assert can_access({pk: "read"}, pk, need_write=False) is True


def test_api_path_to_page_key_insights():
    assert api_path_to_page_key("/api/v1/insights/query") == PageKey.admin_ai_insights


def test_munki_upload_routes_under_software_page_key():
    """The direct-upload endpoint must require ``munki.software`` write access."""
    assert api_path_to_page_key("/api/v1/munki/upload") == PageKey.munki_software


def test_api_path_to_page_key_entity_audit_trails():
    assert api_path_to_page_key("/api/v1/audit/pkg_info/abc") == PageKey.munki_software
    assert api_path_to_page_key("/api/v1/audit/manifest/abc") == PageKey.munki_manifests
    assert api_path_to_page_key("/api/v1/audit/autopkg_recipe/abc") == PageKey.autopkg_recipes


def test_api_path_to_page_key_global_audit_log():
    assert api_path_to_page_key("/api/v1/audit") == PageKey.admin_audit
