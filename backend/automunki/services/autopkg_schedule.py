"""AutoPkg schedule validation, next-run computation, and firing."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from croniter import croniter
from fastapi import HTTPException
from sqlalchemy import select

from automunki.core.db import async_session_factory
from automunki.models.autopkg import AutoPkgSchedule, RunTriggerType
from automunki.services.autopkg_runs import (
    create_and_dispatch_autopkg_run,
    list_recipes_for_run,
    verify_trust_live_for_recipes,
)
from automunki.services.promotion import run_all_auto_promotions

logger = structlog.get_logger()


def assert_valid_cron_expression(expr: str) -> None:
    s = expr.strip()
    parts = s.split()
    if len(parts) != 5:
        raise HTTPException(
            status_code=400,
            detail="Cron must have exactly 5 fields: minute hour day month weekday",
        )
    try:
        croniter(s, datetime.now(UTC))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}") from e


def assert_valid_timezone(tz_name: str) -> None:
    try:
        ZoneInfo(tz_name.strip())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid IANA timezone: {tz_name}") from e


def compute_next_run_at(cron_expr: str, tz_name: str, *, start: datetime | None = None) -> datetime:
    """Next occurrence after ``start`` (UTC), stored as UTC in the database."""
    tz = ZoneInfo(tz_name.strip())
    base = start.astimezone(tz) if start else datetime.now(tz)
    itr = croniter(cron_expr.strip(), base)
    nxt = itr.get_next(datetime)
    return nxt.astimezone(UTC)


async def fire_schedule_by_id(schedule_id: uuid.UUID) -> None:
    """Create a run for this schedule and advance ``next_run_at``."""
    async with async_session_factory() as session:
        sch = await session.get(AutoPkgSchedule, schedule_id)
        if sch is None or not sch.enabled:
            return

        now = datetime.now(UTC)
        candidates = await list_recipes_for_run(session, sch.recipe_names)
        if not candidates:
            logger.info(
                "schedule_no_trust_candidates",
                schedule_id=str(schedule_id),
                schedule_name=sch.name,
            )
            sch.last_run_at = now
            sch.next_run_at = compute_next_run_at(sch.cron_expression, sch.timezone, start=now)
            await session.commit()
            return

        rows, rate_limited = await verify_trust_live_for_recipes(session, candidates)
        verified_names = [r["name"] for r in rows if r["status"] == "verified"]

        if rate_limited:
            logger.warning(
                "schedule_trust_verify_rate_limited",
                schedule_id=str(schedule_id),
                schedule_name=sch.name,
            )

        if not verified_names:
            logger.warning(
                "schedule_trust_verify_no_verified_recipes",
                schedule_id=str(schedule_id),
                schedule_name=sch.name,
            )
            sch.last_run_at = now
            sch.next_run_at = compute_next_run_at(sch.cron_expression, sch.timezone, start=now)
            await session.commit()
            return

        await create_and_dispatch_autopkg_run(
            session,
            recipe_names=verified_names,
            runner_type=sch.runner_type,
            trigger_type=RunTriggerType.scheduled,
            triggered_by=f"schedule:{sch.name}",
            schedule_id=sch.id,
            user_id=None,
            user_email=None,
            audit_action="scheduled_run",
            commit=False,
        )

        sch.last_run_at = now
        sch.next_run_at = compute_next_run_at(sch.cron_expression, sch.timezone, start=now)

        await session.commit()


async def fire_due_schedules() -> None:
    """Run every enabled schedule whose ``next_run_at`` is in the past."""
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        result = await session.execute(
            select(AutoPkgSchedule).where(
                AutoPkgSchedule.enabled.is_(True),
                AutoPkgSchedule.next_run_at.is_not(None),
                AutoPkgSchedule.next_run_at <= now,
            )
        )
        due = [r for r in result.scalars().all()]
    for sch in due:
        try:
            await fire_schedule_by_id(sch.id)
        except Exception:
            logger.error(
                "scheduled_autopkg_run_failed",
                schedule_id=str(sch.id),
                exc_info=True,
            )


async def scheduler_loop(stop: asyncio.Event) -> None:
    """Wake every 60s and fire due schedules."""
    from automunki.core.config import settings

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=60.0)
            break
        except TimeoutError:
            pass
        if not settings.scheduler_enabled:
            continue
        try:
            await fire_due_schedules()
            async with async_session_factory() as promo_session:
                await run_all_auto_promotions(promo_session)
                await promo_session.commit()
        except Exception:
            logger.error("scheduler_tick_failed", exc_info=True)


def schedule_next_for_row(sch: AutoPkgSchedule) -> None:
    """Set ``next_run_at`` when creating/updating a schedule row."""
    sch.next_run_at = compute_next_run_at(sch.cron_expression, sch.timezone)
