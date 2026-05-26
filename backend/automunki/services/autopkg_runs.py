"""Create AutoPkg runs (manual or scheduled) with shared validation and dispatch."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.core.config import settings
from automunki.models.autopkg import AutoPkgRecipe, AutoPkgRun, RunStatus, RunTriggerType, TrustStatus
from automunki.schemas.autopkg import AutoPkgRunRead
from automunki.services.audit import create_audit_entry
from automunki.services.autopkg import dispatch_autopkg_workflow
from automunki.services.trust import (
    build_location_cache,
    persist_verify_trust_result,
    verify_trust,
)

TRUST_STATUS_BLOCKS_RUN = frozenset(
    {TrustStatus.failed.value, TrustStatus.pending_approval.value},
)


async def list_recipes_for_run(
    session: AsyncSession,
    recipe_names: list[str] | None,
) -> list[AutoPkgRecipe]:
    """
    Same candidate set as ``GET /autopkg/runs/config``: enabled overrides whose
    stored trust status does not block runs (failed / pending approval).
    """
    query = select(AutoPkgRecipe).where(AutoPkgRecipe.is_enabled.is_(True))
    result = await session.execute(query)
    all_recipes = [r for r in result.scalars().all() if r.trust_status not in TRUST_STATUS_BLOCKS_RUN]
    if recipe_names:
        names = {str(n).strip() for n in recipe_names if n and str(n).strip()}
        all_recipes = [r for r in all_recipes if r.name in names]
    return all_recipes


async def verify_trust_live_for_recipes(
    session: AsyncSession,
    recipes: list[AutoPkgRecipe],
) -> tuple[list[dict], bool]:
    """
    Compare each recipe's stored trust to live GitHub content; update rows in ``session``.

    Returns ``(result_rows, rate_limited)``. Stops after the first rate-limited response.
    """
    if not recipes:
        return [], False
    location_cache = await build_location_cache(session)
    rows: list[dict] = []
    rate_limited = False
    for recipe in recipes:
        vr = await verify_trust(
            stored_trust_info=recipe.trust_info,
            parent_recipe_identifier=recipe.parent_recipe,
            location_cache=location_cache,
        )
        await persist_verify_trust_result(session, recipe, vr, location_cache)
        rows.append(
            {
                "recipe_id": str(recipe.id),
                "name": recipe.name,
                "status": vr.status,
                "diff": vr.diff if vr.diff else None,
                "error": vr.error,
            }
        )
        if vr.error and "rate limit" in vr.error.lower():
            rate_limited = True
            break
        # GitHub returned 403 for a non-rate-limit reason (PAT scope, org policy,
        # SAML, etc.). Same outcome as rate-limit for the loop: every subsequent
        # recipe will hit the same wall, so stop now and surface what we have.
        if vr.error and "github denied access" in vr.error.lower():
            break
    return rows, rate_limited


async def validation_error_for_recipes(session: AsyncSession, recipe_names: list[str] | None) -> str | None:
    """Return an error message if recipes cannot run, else None."""
    if not recipe_names:
        return None
    res = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.name.in_(recipe_names)))
    found = {r.name: r for r in res.scalars().all()}
    missing = set(recipe_names) - set(found.keys())
    if missing:
        return f"Unknown recipe names: {', '.join(sorted(missing))}"
    blocked = sorted(n for n, r in found.items() if r.trust_status in TRUST_STATUS_BLOCKS_RUN)
    if blocked:
        return f"Cannot run recipes while trust is failed or pending approval: {', '.join(blocked)}"
    return None


async def ensure_recipe_names_runnable(session: AsyncSession, recipe_names: list[str] | None) -> None:
    """Raise HTTPException if any name is unknown or blocked by trust."""
    err = await validation_error_for_recipes(session, recipe_names)
    if err:
        raise HTTPException(status_code=400, detail=err)


def normalize_runner_type(runner: str | None) -> str:
    r = runner if runner is not None else settings.autopkg_runner_mode
    if r not in ("github", "local"):
        return "github"
    return r


async def create_and_dispatch_autopkg_run(
    session: AsyncSession,
    *,
    recipe_names: list[str] | None,
    runner_type: str,
    trigger_type: RunTriggerType,
    triggered_by: str | None,
    schedule_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
    audit_action: str = "trigger_run",
    commit: bool = True,
) -> AutoPkgRun:
    """Validate recipes, create run row, dispatch GitHub or leave local pending, audit, commit."""
    await ensure_recipe_names_runnable(session, recipe_names)

    run = AutoPkgRun(
        status=RunStatus.pending,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        recipe_filter=recipe_names,
        runner_type=runner_type,
        schedule_id=schedule_id,
    )
    session.add(run)
    await session.flush()

    if runner_type == "local":
        result: dict = {"status": "local_pending"}
    else:
        result = await dispatch_autopkg_workflow(
            run_id=str(run.id),
            recipe_names=recipe_names,
        )

    if "error" in result:
        run.status = RunStatus.failed
        run.error_message = result["error"]
    elif result.get("status") == "local_pending":
        run.status = RunStatus.pending
        run.error_message = None
    else:
        run.status = RunStatus.running
        run.started_at = datetime.now(UTC)

    after_snapshot: dict = {"recipe_filter": recipe_names}
    if schedule_id:
        after_snapshot["schedule_id"] = str(schedule_id)

    await create_audit_entry(
        session,
        action=audit_action,
        entity_type="autopkg_run",
        entity_id=str(run.id),
        user_id=user_id,
        user_email=user_email,
        after_snapshot=after_snapshot,
    )

    if commit:
        await session.commit()
        await session.refresh(run)
    return run


def autopkg_run_to_read(run: AutoPkgRun) -> AutoPkgRunRead:
    """Build API model; set ``schedule_name`` when ``run.schedule`` is loaded."""
    r = AutoPkgRunRead.model_validate(run)
    sch = getattr(run, "schedule", None)
    if run.schedule_id and sch is not None:
        return r.model_copy(update={"schedule_name": sch.name})
    return r
