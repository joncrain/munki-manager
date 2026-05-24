"""AutoPkg schedule helpers and RBAC path mapping."""

from datetime import UTC

import pytest
from fastapi import HTTPException

from automunki.core.page_keys import PageKey, api_path_to_page_key
from automunki.services.autopkg_schedule import (
    assert_valid_cron_expression,
    assert_valid_timezone,
    compute_next_run_at,
)


def test_api_path_autopkg_schedules():
    assert api_path_to_page_key("/api/v1/autopkg/schedules") == PageKey.autopkg_runs
    assert api_path_to_page_key("/api/v1/autopkg/schedules/abc") == PageKey.autopkg_runs


def test_api_path_autopkg_trust_changes_maps_to_approvals():
    assert api_path_to_page_key("/api/v1/autopkg/trust-changes") == PageKey.autopkg_approvals
    assert api_path_to_page_key("/api/v1/autopkg/trust-changes/pending-count") == PageKey.autopkg_approvals


def test_assert_valid_cron_ok():
    assert_valid_cron_expression("0 * * * *")


def test_assert_valid_cron_bad():
    with pytest.raises(HTTPException) as exc:
        assert_valid_cron_expression("not a cron")
    assert exc.value.status_code == 400


def test_assert_valid_timezone():
    assert_valid_timezone("UTC")
    with pytest.raises(HTTPException):
        assert_valid_timezone("Not/AZone")


def test_compute_next_run_at_utc():
    n = compute_next_run_at("0 * * * *", "UTC")
    assert n.tzinfo == UTC
