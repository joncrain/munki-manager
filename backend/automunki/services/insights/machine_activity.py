"""Filter fleet machines by recent check-in activity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select

from automunki.models.client import ClientMachine

DEFAULT_ACTIVE_WITHIN_DAYS = 5


def apply_active_machine_filter(
    query: Select[tuple[ClientMachine]],
    *,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
) -> Select[tuple[ClientMachine]]:
    """Restrict to machines that checked in within ``active_within_days``.

    Pass ``None`` to include the entire enrolled fleet (including stale machines).
    """
    if active_within_days is None:
        return query
    cutoff = datetime.now(UTC) - timedelta(days=max(1, active_within_days))
    return query.where(ClientMachine.last_checkin_at >= cutoff)
