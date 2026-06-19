"""Tests for install report insight handlers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from automunki.services.insights.handlers_install_reports import (
    categorize_install_reason,
    get_failed_install_summary,
    get_install_counts_by_version,
    get_install_popularity,
)


def test_categorize_install_reason():
    assert categorize_install_reason("managed_install") == "managed"
    assert categorize_install_reason("managed_update") == "managed"
    assert categorize_install_reason("optional_install") == "optional"
    assert categorize_install_reason("removal") == "other"
    assert categorize_install_reason(None) == "other"


@pytest.mark.asyncio
async def test_get_install_popularity_managed_vs_optional():
    rows = [
        ("GoogleChrome", "managed_install", uuid4()),
        ("GoogleChrome", "managed_update", uuid4()),
        ("Slack", "optional_install", uuid4()),
        ("Slack", "optional_install", uuid4()),
    ]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    data = await get_install_popularity(session, days_back=90, active_within_days=5)

    assert len(data["rankings"]) == 2
    chrome = next(item for item in data["rankings"] if item["item_name"] == "GoogleChrome")
    slack = next(item for item in data["rankings"] if item["item_name"] == "Slack")
    assert chrome["by_category"]["managed"] == 2
    assert slack["by_category"]["optional"] == 2


@pytest.mark.asyncio
async def test_get_install_popularity_optional_filter():
    rows = [
        ("Slack", "optional_install", uuid4()),
        ("GoogleChrome", "managed_install", uuid4()),
    ]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    data = await get_install_popularity(
        session,
        install_reason_category="optional",
    )

    assert len(data["rankings"]) == 1
    assert data["rankings"][0]["item_name"] == "Slack"


@pytest.mark.asyncio
async def test_get_install_counts_by_version():
    rows = [
        ("149.0.7827.156", "installed", "managed_install", uuid4()),
        ("149.0.7827.156", "installed", "managed_update", uuid4()),
        ("148.0.7000.0", "failed", "managed_update", uuid4()),
    ]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    with patch(
        "automunki.services.insights.handlers_install_reports._resolve_catalog_item_name",
        new=AsyncMock(return_value="GoogleChrome"),
    ):
        data = await get_install_counts_by_version(session, query="chrome")

    assert data["item_name"] == "GoogleChrome"
    assert data["total_events"] == 3
    assert data["version_breakdown"][0]["version"] == "149.0.7827.156"
    assert data["version_breakdown"][0]["event_count"] == 2


@pytest.mark.asyncio
async def test_get_failed_install_summary():
    now = datetime.now(UTC)
    rows = [
        (
            "GoogleChrome",
            "149.0.7827.156",
            "Installation failed: exit 1",
            "managed_update",
            uuid4(),
            now - timedelta(days=1),
            now - timedelta(days=1),
            "mac-1",
            "S1",
        ),
        (
            "GoogleChrome",
            "149.0.7827.156",
            "Installation failed: exit 1",
            "managed_update",
            uuid4(),
            now - timedelta(days=2),
            now - timedelta(days=2),
            "mac-2",
            "S2",
        ),
        (
            "Slack",
            "4.40.0",
            "Disk full",
            "optional_install",
            uuid4(),
            now - timedelta(days=3),
            now - timedelta(days=3),
            "mac-3",
            "S3",
        ),
    ]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))

    data = await get_failed_install_summary(session, days_back=90)

    assert data["total_failures"] == 3
    assert data["by_item"][0]["item_name"] == "GoogleChrome"
    assert data["by_item"][0]["failure_count"] == 2
    assert len(data["recent_failures"]) == 3
    assert data["recent_failures"][0]["item_name"] == "GoogleChrome"
