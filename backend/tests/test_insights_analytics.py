"""Tests for extended insights analytics handlers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from automunki.models.autopkg import RecipeResultStatus
from automunki.services.insights import handlers_analytics
from automunki.services.insights.hardware_match import machine_matches_hardware


def test_machine_matches_hardware_mac_studio():
    machine = SimpleNamespace(
        machine_model="Mac13,1",
        hardware_info={"product_name": "Mac Studio", "apple_image_family": "Mac Studio"},
    )
    assert machine_matches_hardware(machine, "Mac Studio")
    assert machine_matches_hardware(machine, "mac studio")
    assert not machine_matches_hardware(machine, "MacBook Air")


def test_machine_matches_hardware_empty_query():
    machine = SimpleNamespace(machine_model="Mac14,2", hardware_info={})
    assert machine_matches_hardware(machine, None)
    assert machine_matches_hardware(machine, "")


@pytest.mark.asyncio
async def test_get_pkginfo_update_age():
    now = datetime.now(UTC)
    pkg = SimpleNamespace(
        id=uuid4(),
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=3),
    )
    catalog_row = ("production", now - timedelta(days=5))

    session = AsyncMock()

    async def fake_execute(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "munki_pkginfo_catalog" in sql:
            result.all.return_value = [catalog_row]
        else:
            result.scalar_one_or_none.return_value = pkg
        return result

    session.execute = fake_execute

    with patch(
        "automunki.services.insights.handlers_analytics.get_catalog_latest_version",
        new=AsyncMock(
            return_value={
                "item_name": "GoogleChrome",
                "display_name": "Google Chrome",
                "latest_version": "149.0.7827.156",
            }
        ),
    ):
        data = await handlers_analytics.get_pkginfo_update_age(session, query="chrome")

    assert data["item_name"] == "GoogleChrome"
    assert data["days_since_pkginfo_created"] == 10.0
    assert data["days_since_pkginfo_updated"] == 3.0
    assert data["days_since_first_catalog_entry"] == 5.0


@pytest.mark.asyncio
async def test_get_adoption_timeline_threshold_reached():
    now = datetime.now(UTC)
    release = now - timedelta(days=14)
    installs = [
        (uuid4(), now - timedelta(days=10), now - timedelta(days=10)),
        (uuid4(), now - timedelta(days=8), now - timedelta(days=8)),
        (uuid4(), now - timedelta(days=6), now - timedelta(days=6)),
        (uuid4(), now - timedelta(days=4), now - timedelta(days=4)),
        (uuid4(), now - timedelta(days=2), now - timedelta(days=2)),
    ]
    pkg = SimpleNamespace(id=uuid4(), created_at=release)

    session = AsyncMock()

    count_fleet = MagicMock()
    count_fleet.scalar.return_value = 5
    count_ever = MagicMock()
    count_ever.scalar.return_value = 5
    min_cat = MagicMock()
    min_cat.scalar_one_or_none.return_value = release
    install_list = MagicMock()
    install_list.all.return_value = installs
    pkg_result = MagicMock()
    pkg_result.scalar_one_or_none.return_value = pkg

    session.execute = AsyncMock(side_effect=[pkg_result, min_cat, install_list, count_fleet, count_ever])

    with patch(
        "automunki.services.insights.handlers_analytics.get_catalog_latest_version",
        new=AsyncMock(return_value={"item_name": "GoogleChrome", "latest_version": "149.0.7827.156"}),
    ):
        data = await handlers_analytics.get_adoption_timeline(session, query="chrome", threshold_percent=80.0)

    assert data["threshold_reached"] is True
    assert data["machines_on_target_version"] == 5
    assert data["days_to_threshold"] is not None


@pytest.mark.asyncio
async def test_count_machines_with_software_hardware_filter():
    machine_studio = SimpleNamespace(
        hostname="studio-1",
        serial_number="S1",
        machine_model="Mac13,1",
        hardware_info={"product_name": "Mac Studio"},
        installed_software=[{"name": "GoogleChrome", "version": "149.0.7827.156", "bundle_id": "com.google.Chrome"}],
        last_checkin_at=datetime.now(UTC) - timedelta(days=1),
    )
    machine_air = SimpleNamespace(
        hostname="air-1",
        serial_number="A1",
        machine_model="Mac14,2",
        hardware_info={"product_name": "MacBook Air"},
        installed_software=[{"name": "GoogleChrome", "version": "149.0.7827.156", "bundle_id": "com.google.Chrome"}],
        last_checkin_at=datetime.now(UTC) - timedelta(days=1),
    )

    session = AsyncMock()
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [machine_studio, machine_air]
    session.execute = AsyncMock(return_value=list_result)

    with patch(
        "automunki.services.insights.handlers_analytics.expand_software_matchers",
        new=AsyncMock(return_value={"matchers": ["googlechrome"], "resolution": {}}),
    ):
        data = await handlers_analytics.count_machines_with_software(
            session, query="chrome", hardware_query="Mac Studio"
        )

    assert data["machine_count"] == 1
    assert data["machines"][0]["hostname"] == "studio-1"


@pytest.mark.asyncio
async def test_get_autopkg_release_history():
    now = datetime.now(UTC)
    imports = [
        SimpleNamespace(
            created_at=now - timedelta(days=30),
            status=RecipeResultStatus.imported,
            imported_version="148.0.7000.0",
            recipe_name="GoogleChrome",
        ),
        SimpleNamespace(
            created_at=now - timedelta(days=10),
            status=RecipeResultStatus.imported,
            imported_version="149.0.7827.156",
            recipe_name="GoogleChrome",
        ),
        SimpleNamespace(
            created_at=now - timedelta(days=5),
            status=RecipeResultStatus.no_change,
            imported_version=None,
            recipe_name="GoogleChrome",
        ),
    ]

    session = AsyncMock()
    recipe_result = MagicMock()
    recipe_result.all.return_value = [("GoogleChrome", "com.github.autopkg.munki.googlechrome")]
    import_result = MagicMock()
    import_result.all.return_value = imports
    session.execute = AsyncMock(side_effect=[recipe_result, import_result])

    with patch(
        "automunki.services.insights.handlers_analytics._resolve_catalog_item_name",
        new=AsyncMock(return_value="GoogleChrome"),
    ):
        data = await handlers_analytics.get_autopkg_release_history(session, query="chrome", days_back=365)

    assert data["new_version_imports"] == 2
    assert data["average_days_between_imports"] == 20.0
    assert len(data["releases"]) == 2
