"""Filter fleet machines by recent check-in activity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select

from automunki.models.client import ClientMachine

DEFAULT_ACTIVE_WITHIN_DAYS = 5


def active_machine_checkin_cutoff(*, active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS) -> datetime | None:
    """Return the earliest ``last_checkin_at`` to count as active, or ``None`` for no filter."""
    if active_within_days is None:
        return None
    return datetime.now(UTC) - timedelta(days=max(1, active_within_days))


def apply_active_machine_filter(
    query: Select[tuple[ClientMachine]],
    *,
    active_within_days: int | None = DEFAULT_ACTIVE_WITHIN_DAYS,
) -> Select[tuple[ClientMachine]]:
    """Restrict to machines that checked in within ``active_within_days``.

    Pass ``None`` to include the entire enrolled fleet (including stale machines).
    """
    cutoff = active_machine_checkin_cutoff(active_within_days=active_within_days)
    if cutoff is None:
        return query
    return query.where(ClientMachine.last_checkin_at >= cutoff)
