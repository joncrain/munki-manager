"""RBAC paths for promotion channels and workflow preferences."""

from automunki.core.page_keys import PageKey, api_path_to_page_key


def test_promotion_channels_maps_to_catalogs():
    assert api_path_to_page_key("/api/v1/promotion-channels") == PageKey.munki_catalogs


def test_workflow_preferences_maps_to_approvals():
    assert api_path_to_page_key("/api/v1/workflow/preferences") == PageKey.autopkg_approvals


def test_autopkg_promotions_webhook_maps_to_runs():
    assert api_path_to_page_key("/api/v1/autopkg/promotions/run-due") == PageKey.autopkg_runs
