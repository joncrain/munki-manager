"""Tests for active-machine filtering in insights."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from automunki.models.client import ClientMachine
from automunki.services.insights.machine_activity import apply_active_machine_filter


def test_apply_active_machine_filter_adds_checkin_predicate():
    stmt = apply_active_machine_filter(select(ClientMachine), active_within_days=5)
    compiled = str(stmt)
    assert "last_checkin_at" in compiled


def test_apply_active_machine_filter_none_skips_predicate():
    base = select(ClientMachine)
    stmt = apply_active_machine_filter(base, active_within_days=None)
    assert str(stmt) == str(base)


@pytest.mark.asyncio
async def test_count_machines_excludes_stale_checkins():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from automunki.services.insights import handlers_analytics

    now = datetime.now(UTC)
    active = SimpleNamespace(
        hostname="active-mac",
        serial_number="A1",
        machine_model="Mac13,1",
        hardware_info={"product_name": "Mac Studio"},
        installed_software=[{"name": "GoogleChrome", "version": "149.0", "bundle_id": "com.google.Chrome"}],
        last_checkin_at=now - timedelta(days=1),
    )

    session = AsyncMock()
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [active]
    session.execute = AsyncMock(return_value=list_result)

    with patch(
        "automunki.services.insights.handlers_analytics.expand_software_matchers",
        new=AsyncMock(return_value={"matchers": ["googlechrome"], "resolution": {}}),
    ):
        data = await handlers_analytics.count_machines_with_software(
            session, query="chrome", hardware_query="Mac Studio", active_within_days=5
        )

    assert data["machine_count"] == 1
    assert data["active_within_days"] == 5
    assert data["machines"][0]["hostname"] == "active-mac"
