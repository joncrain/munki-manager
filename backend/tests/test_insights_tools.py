"""Unit tests for insights tool helpers and handlers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from automunki.services.insights import handlers
from automunki.services.insights.software_resolve import software_entry_matches
from automunki.services.insights.tools import (
    INSIGHT_TOOLS,
    execute_tool,
    extract_table,
    gemini_function_declarations,
    summarize_tool_result,
)


def test_insight_tools_registry_has_fifteen_tools():
    assert len(INSIGHT_TOOLS) == 15
    assert "resolve_software_identity" in INSIGHT_TOOLS
    assert "compare_fleet_version_to_latest" in INSIGHT_TOOLS
    assert "get_pkginfo_update_age" in INSIGHT_TOOLS
    assert "get_adoption_timeline" in INSIGHT_TOOLS
    assert "get_autopkg_release_history" in INSIGHT_TOOLS
    assert "count_machines_with_software" in INSIGHT_TOOLS
    assert "get_install_popularity" in INSIGHT_TOOLS
    assert "get_failed_install_summary" in INSIGHT_TOOLS


def test_gemini_function_declarations_count():
    decls = gemini_function_declarations()
    assert len(decls) == 15
    assert decls[0].name in INSIGHT_TOOLS


def test_software_entry_matches_aliases():
    entry = {
        "name": "GoogleChrome",
        "version": "149.0.7827.156",
        "bundle_id": "com.google.Chrome",
    }
    assert software_entry_matches(entry, ["googlechrome"])
    assert software_entry_matches(entry, ["google chrome"])
    assert software_entry_matches(entry, ["com.google.chrome"])


def test_version_sort_key_orders_numeric_segments():
    versions = ["149.0.7827.156", "148.0.7000.0", "149.0.7827.155"]
    latest = max(versions, key=handlers._version_sort_key)
    assert latest == "149.0.7827.156"


def test_extract_table_from_handler_result():
    result = {
        "table": {
            "columns": ["hostname", "serial_number"],
            "rows": [["mac-1", "ABC123"]],
        }
    }
    table = extract_table(result)
    assert table is not None
    assert table["columns"] == ["hostname", "serial_number"]


@pytest.mark.asyncio
async def test_get_fleet_compliance_with_mock_session():
    session = AsyncMock()

    async def fake_execute(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "count" in sql.lower():
            if "last_checkin_at >=" in sql:
                result.scalar.return_value = 80
            elif "last_checkin_at <" in sql:
                result.scalar.return_value = 10
            else:
                result.scalar.return_value = 100
        return result

    session.execute = fake_execute
    data = await handlers.get_fleet_compliance(session)
    assert data["total_machines"] == 100
    assert data["checked_in_last_7_days"] == 80
    assert data["stale_over_30_days"] == 10
    assert data["compliance_percentage"] == 80.0


@pytest.mark.asyncio
async def test_list_stale_machines_returns_table():
    stale_at = datetime.now(UTC) - timedelta(days=45)
    machine = SimpleNamespace(
        hostname="test-mac",
        serial_number="C02TEST123",
        manifest_name="standard",
        last_checkin_at=stale_at,
    )

    count_result = MagicMock()
    count_result.scalar.return_value = 1

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [machine]

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[count_result, list_result])

    data = await handlers.list_stale_machines(session, days=30, limit=10)
    assert data["total_stale"] == 1
    assert data["machines"][0]["hostname"] == "test-mac"
    assert data["table"]["rows"][0][1] == "C02TEST123"


@pytest.mark.asyncio
async def test_execute_tool_unknown_name():
    session = AsyncMock()
    result = await execute_tool(session, "nonexistent_tool", {})
    assert "error" in result


def test_summarize_tool_result_compliance():
    summary = summarize_tool_result(
        "get_fleet_compliance",
        {"total_machines": 10, "checked_in_last_7_days": 8, "stale_over_30_days": 2},
    )
    assert "10 machines" in summary
