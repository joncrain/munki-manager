"""Install report analytics for AI insights (popularity, versions, failures)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.client import ClientInstallReport, ClientMachine
from automunki.services.insights.handlers import _resolve_catalog_item_name
from automunki.services.insights.machine_activity import (
    DEFAULT_ACTIVE_WITHIN_DAYS,
    active_machine_checkin_cutoff,
)

InstallReasonCategory = Literal["managed", "optional", "other"]

MANAGED_INSTALL_REASONS = frozenset({"managed_install", "managed_update"})
OPTIONAL_INSTALL_REASONS = frozenset({"optional_install"})

UNKNOWN_VERSION = "unknown"


def categorize_install_reason(reason: str | None) -> InstallReasonCategory:
    if reason in MANAGED_INSTALL_REASONS:
        return "managed"
    if reason in OPTIONAL_INSTALL_REASONS:
        return "optional"
    return "other"


def _event_timestamp():
    return func.coalesce(ClientInstallReport.install_date, ClientInstallReport.created_at)


def _apply_install_report_scope(
    query,
    *,
    days_back: int,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
):
    event_ts = _event_timestamp()
    cutoff = datetime.now(UTC) - timedelta(days=max(1, days_back))
    query = query.where(event_ts >= cutoff)
    active_cutoff = active_machine_checkin_cutoff(active_within_days=active_within_days)
    if active_cutoff is not None:
        query = query.where(ClientMachine.last_checkin_at >= active_cutoff)
    return query


async def get_install_popularity(
    session: AsyncSession,
    *,
    days_back: int = 90,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
    status: str = "installed",
    install_reason_category: InstallReasonCategory | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Rank software by install report volume, with managed vs optional breakdown."""
    query = (
        select(
            ClientInstallReport.item_name,
            ClientInstallReport.install_reason,
            ClientInstallReport.machine_id,
        )
        .join(ClientMachine, ClientInstallReport.machine_id == ClientMachine.id)
        .where(ClientInstallReport.status == status)
    )
    query = _apply_install_report_scope(
        query,
        days_back=days_back,
        active_within_days=active_within_days,
    )

    rows = (await session.execute(query)).all()

    by_item_events: Counter[str] = Counter()
    by_item_machines: dict[str, set[Any]] = defaultdict(set)
    by_item_reason: dict[str, Counter[str]] = defaultdict(Counter)
    by_item_category: dict[str, Counter[str]] = defaultdict(Counter)

    for item_name, reason, machine_id in rows:
        category = categorize_install_reason(reason)
        if install_reason_category is not None and category != install_reason_category:
            continue
        by_item_events[item_name] += 1
        by_item_machines[item_name].add(machine_id)
        reason_key = reason or "unknown"
        by_item_reason[item_name][reason_key] += 1
        by_item_category[item_name][category] += 1

    rankings = sorted(
        by_item_events.keys(),
        key=lambda name: (-by_item_events[name], name),
    )[:limit]

    items = [
        {
            "item_name": name,
            "event_count": by_item_events[name],
            "unique_machines": len(by_item_machines[name]),
            "by_install_reason": dict(by_item_reason[name]),
            "by_category": dict(by_item_category[name]),
        }
        for name in rankings
    ]

    table_rows = [
        [
            item["item_name"],
            item["event_count"],
            item["unique_machines"],
            item["by_category"].get("managed", 0),
            item["by_category"].get("optional", 0),
        ]
        for item in items
    ]

    return {
        "days_back": days_back,
        "active_within_days": active_within_days,
        "status_filter": status,
        "install_reason_category_filter": install_reason_category,
        "rankings": items,
        "table": {
            "columns": [
                "item_name",
                "event_count",
                "unique_machines",
                "managed_installs",
                "optional_installs",
            ],
            "rows": table_rows,
        },
    }


async def get_install_counts_by_version(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    days_back: int = 90,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
    status: str | None = None,
) -> dict[str, Any]:
    """Install report counts for one title, grouped by version (and status when unfiltered)."""
    hint = (query or item_name or "").strip()
    if not hint:
        return {"error": "Provide query or item_name"}

    name = await _resolve_catalog_item_name(session, hint)

    base = (
        select(
            ClientInstallReport.item_version,
            ClientInstallReport.status,
            ClientInstallReport.install_reason,
            ClientInstallReport.machine_id,
        )
        .join(ClientMachine, ClientInstallReport.machine_id == ClientMachine.id)
        .where(ClientInstallReport.item_name == name)
    )
    if status:
        base = base.where(ClientInstallReport.status == status)
    base = _apply_install_report_scope(
        base,
        days_back=days_back,
        active_within_days=active_within_days,
    )

    rows = (await session.execute(base)).all()

    version_events: Counter[str] = Counter()
    version_machines: dict[str, set[Any]] = defaultdict(set)
    version_by_reason: dict[str, Counter[str]] = defaultdict(Counter)
    version_by_status: dict[str, Counter[str]] = defaultdict(Counter)

    for item_version, row_status, reason, machine_id in rows:
        version = item_version or UNKNOWN_VERSION
        version_events[version] += 1
        version_machines[version].add(machine_id)
        version_by_reason[version][reason or "unknown"] += 1
        version_by_status[version][row_status] += 1

    versions = sorted(
        version_events.keys(),
        key=lambda v: (-version_events[v], v),
    )

    breakdown = [
        {
            "version": version,
            "event_count": version_events[version],
            "unique_machines": len(version_machines[version]),
            "by_install_reason": dict(version_by_reason[version]),
            "by_status": dict(version_by_status[version]),
        }
        for version in versions
    ]

    table_rows = [[entry["version"], entry["event_count"], entry["unique_machines"]] for entry in breakdown]

    return {
        "item_name": name,
        "query": hint,
        "days_back": days_back,
        "active_within_days": active_within_days,
        "status_filter": status,
        "total_events": sum(version_events.values()),
        "version_breakdown": breakdown,
        "table": {
            "columns": ["version", "event_count", "unique_machines"],
            "rows": table_rows,
        },
    }


async def get_failed_install_summary(
    session: AsyncSession,
    *,
    days_back: int = 90,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
    query: str | None = None,
    item_name: str | None = None,
    limit: int = 20,
    recent_failure_limit: int = 25,
) -> dict[str, Any]:
    """Rank software by failed install count and return recent failure details."""
    name_filter: str | None = None
    hint = (query or item_name or "").strip()
    if hint:
        name_filter = await _resolve_catalog_item_name(session, hint)

    failure_query = (
        select(
            ClientInstallReport.item_name,
            ClientInstallReport.item_version,
            ClientInstallReport.error_message,
            ClientInstallReport.install_reason,
            ClientInstallReport.machine_id,
            ClientInstallReport.install_date,
            ClientInstallReport.created_at,
            ClientMachine.hostname,
            ClientMachine.serial_number,
        )
        .join(ClientMachine, ClientInstallReport.machine_id == ClientMachine.id)
        .where(ClientInstallReport.status == "failed")
    )
    if name_filter:
        failure_query = failure_query.where(ClientInstallReport.item_name == name_filter)
    failure_query = _apply_install_report_scope(
        failure_query,
        days_back=days_back,
        active_within_days=active_within_days,
    )

    rows = (await session.execute(failure_query)).all()

    by_item: Counter[str] = Counter()
    by_item_machines: dict[str, set[Any]] = defaultdict(set)
    by_item_errors: dict[str, Counter[str]] = defaultdict(Counter)

    recent_failures: list[dict[str, Any]] = []

    for (
        item,
        item_version,
        error_message,
        reason,
        machine_id,
        install_date,
        created_at,
        hostname,
        serial_number,
    ) in rows:
        by_item[item] += 1
        by_item_machines[item].add(machine_id)
        err = (error_message or "No error message recorded").strip()
        by_item_errors[item][err] += 1

        event_ts = install_date or created_at
        recent_failures.append(
            {
                "item_name": item,
                "item_version": item_version,
                "error_message": error_message,
                "install_reason": reason,
                "hostname": hostname,
                "serial_number": serial_number,
                "event_at": event_ts.isoformat() if event_ts else None,
                "_sort_ts": event_ts or datetime.min.replace(tzinfo=UTC),
            }
        )

    recent_failures.sort(key=lambda row: row["_sort_ts"], reverse=True)
    for row in recent_failures:
        row.pop("_sort_ts", None)

    top_items = sorted(by_item.keys(), key=lambda n: (-by_item[n], n))[:limit]

    by_item_summary = [
        {
            "item_name": item,
            "failure_count": by_item[item],
            "unique_machines": len(by_item_machines[item]),
            "top_error_messages": [
                {"message": msg, "count": count} for msg, count in by_item_errors[item].most_common(3)
            ],
        }
        for item in top_items
    ]

    failure_table_rows = [
        [
            item["item_name"],
            item["failure_count"],
            item["unique_machines"],
            item["top_error_messages"][0]["message"] if item["top_error_messages"] else None,
        ]
        for item in by_item_summary
    ]

    recent_table_rows = [
        [
            row["item_name"],
            row["item_version"],
            row["hostname"],
            row["error_message"],
            row["event_at"],
        ]
        for row in recent_failures[:recent_failure_limit]
    ]

    return {
        "days_back": days_back,
        "active_within_days": active_within_days,
        "item_name_filter": name_filter,
        "total_failures": sum(by_item.values()),
        "distinct_items_with_failures": len(by_item),
        "by_item": by_item_summary,
        "recent_failures": recent_failures[:recent_failure_limit],
        "table": {
            "columns": ["item_name", "failure_count", "unique_machines", "top_error"],
            "rows": failure_table_rows,
        },
        "recent_failures_table": {
            "columns": ["item_name", "version", "hostname", "error_message", "event_at"],
            "rows": recent_table_rows,
        },
    }
