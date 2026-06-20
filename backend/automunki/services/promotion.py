"""Promotion engine for moving pkginfo between catalogs."""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from automunki.models.autopkg import AutoPkgRecipe
from automunki.models.munki import (
    Catalog,
    PkgInfo,
    PkgInfoCatalog,
    PromotionChannel,
    PromotionChannelStep,
    PromotionRule,
    PromotionStrategy,
)
from automunki.services.audit import create_audit_entry
from automunki.services.recipe_input_merge import merged_recipe_input
from automunki.services.shard_rollout import maybe_init_shard_after_catalog_change

logger = structlog.get_logger()


def recipe_pkginfo_name_key(recipe: AutoPkgRecipe) -> str:
    m = merged_recipe_input(recipe)
    n = m.get("NAME") if m else None
    if isinstance(n, str) and n.strip():
        return n.strip()
    return recipe.name


async def promote_pkginfo(
    session: AsyncSession,
    *,
    pkg_info_id: uuid.UUID,
    target_catalog_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
) -> bool:
    """Promote a PkgInfo to a target catalog."""
    pkg = await session.get(PkgInfo, pkg_info_id)
    if not pkg:
        return False

    target_catalog = await session.get(Catalog, target_catalog_id)
    if not target_catalog:
        return False

    existing = await session.execute(
        select(PkgInfoCatalog).where(
            PkgInfoCatalog.pkg_info_id == pkg_info_id,
            PkgInfoCatalog.catalog_id == target_catalog_id,
        )
    )
    if existing.scalar_one_or_none():
        return True

    before_catalogs = [c.name for c in pkg.catalogs]

    session.add(
        PkgInfoCatalog(
            pkg_info_id=pkg_info_id,
            catalog_id=target_catalog_id,
            entered_at=datetime.now(UTC),
        )
    )

    await session.flush()
    pkg_sync = (
        await session.execute(select(PkgInfo).options(selectinload(PkgInfo.catalogs)).where(PkgInfo.id == pkg_info_id))
    ).scalar_one()

    after_catalogs = [c.name for c in pkg_sync.catalogs]
    await create_audit_entry(
        session,
        action="promote",
        entity_type="pkg_info",
        entity_id=str(pkg_info_id),
        entity_name=f"{pkg.name} {pkg.version}",
        user_id=user_id,
        user_email=user_email,
        before_snapshot={"catalogs": before_catalogs},
        after_snapshot={"catalogs": after_catalogs},
        notes=f"Promoted to {target_catalog.name}",
    )

    await session.flush()
    logger.info(
        "pkginfo_promoted",
        pkg_name=pkg.name,
        version=pkg.version,
        target_catalog=target_catalog.name,
    )
    await maybe_init_shard_after_catalog_change(session, pkg_info_id)
    return True


async def check_auto_promotions(session: AsyncSession) -> list[dict]:
    """Check and execute time-based auto-promotions."""
    result = await session.execute(
        select(PromotionRule).where(
            PromotionRule.strategy == PromotionStrategy.auto_time,
            PromotionRule.auto_promote_days.isnot(None),
        )
    )
    rules = result.scalars().all()
    promoted = []

    for rule in rules:
        cutoff = datetime.now(UTC) - timedelta(days=rule.auto_promote_days)
        pkg_result = await session.execute(
            select(PkgInfo)
            .join(PkgInfoCatalog, PkgInfo.id == PkgInfoCatalog.pkg_info_id)
            .where(
                PkgInfoCatalog.catalog_id == rule.source_catalog_id,
                PkgInfo.name == rule.pkginfo_name,
                PkgInfo.is_deleted.is_(False),
                PkgInfo.created_at <= cutoff,
            )
        )
        eligible = pkg_result.scalars().all()

        for pkg in eligible:
            already = await session.execute(
                select(PkgInfoCatalog).where(
                    PkgInfoCatalog.pkg_info_id == pkg.id,
                    PkgInfoCatalog.catalog_id == rule.target_catalog_id,
                )
            )
            if already.scalar_one_or_none():
                continue

            success = await promote_pkginfo(
                session,
                pkg_info_id=pkg.id,
                target_catalog_id=rule.target_catalog_id,
                user_email="system:auto-promotion",
            )
            if success:
                promoted.append(
                    {
                        "name": pkg.name,
                        "version": pkg.version,
                        "target_catalog_id": str(rule.target_catalog_id),
                    }
                )

    return promoted


async def _apply_channel_step(
    session: AsyncSession,
    *,
    pkg: PkgInfo,
    step: PromotionChannelStep,
    user_email: str,
) -> bool:
    """Remove pkg from step's source catalog and ensure membership in target."""
    await session.execute(
        delete(PkgInfoCatalog).where(
            PkgInfoCatalog.pkg_info_id == pkg.id,
            PkgInfoCatalog.catalog_id == step.source_catalog_id,
        )
    )
    await session.flush()
    return await promote_pkginfo(
        session,
        pkg_info_id=pkg.id,
        target_catalog_id=step.target_catalog_id,
        user_email=user_email,
    )


async def run_promotion_channel_tick(session: AsyncSession) -> list[dict]:
    """Time-based moves: each ``PkgInfo`` with ``auto_promote`` and ``promotion_channel_id`` is processed."""
    ch_result = await session.execute(select(PromotionChannel).options(selectinload(PromotionChannel.steps)))
    channels: dict[uuid.UUID, PromotionChannel] = {c.id: c for c in ch_result.scalars().all()}

    pkg_result = await session.execute(
        select(PkgInfo).where(
            PkgInfo.is_deleted.is_(False),
            PkgInfo.auto_promote.is_(True),
            PkgInfo.promotion_channel_id.isnot(None),
        )
    )
    packages = pkg_result.scalars().all()
    now = datetime.now(UTC)
    promoted: list[dict] = []

    for pkg in packages:
        ch_id = pkg.promotion_channel_id
        if not ch_id or ch_id not in channels:
            continue
        channel = channels[ch_id]
        steps = sorted(channel.steps, key=lambda s: s.step_order)
        if not steps:
            continue
        for step in steps:
            link = (
                await session.execute(
                    select(PkgInfoCatalog).where(
                        PkgInfoCatalog.pkg_info_id == pkg.id,
                        PkgInfoCatalog.catalog_id == step.source_catalog_id,
                    )
                )
            ).scalar_one_or_none()
            if not link:
                continue
            if step.dwell_days <= 0:
                eligible = True
            else:
                eligible_at = link.entered_at + timedelta(days=step.dwell_days)
                eligible = now >= eligible_at
            if not eligible:
                continue
            ok = await _apply_channel_step(
                session,
                pkg=pkg,
                step=step,
                user_email="system:promotion-channel",
            )
            if ok:
                tgt = await session.get(Catalog, step.target_catalog_id)
                promoted.append(
                    {
                        "name": pkg.name,
                        "version": pkg.version,
                        "channel": channel.name,
                        "target_catalog": tgt.name if tgt else str(step.target_catalog_id),
                    }
                )
            break

    return promoted


@dataclass
class _LegPreview:
    step_order: int
    source_catalog_name: str
    target_catalog_name: str
    dwell_days: int
    promote_at: datetime
    days_remaining: int
    status: str
    dwell_clock_start_at: datetime


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _days_remaining_ceil(now: datetime, target: datetime) -> int:
    if target <= now:
        return 0
    return max(0, int(math.ceil((target - now).total_seconds() / 86400.0)))


def _build_leg_previews(
    ch: PromotionChannel,
    link_by_cat_id: dict[uuid.UUID, PkgInfoCatalog],
    cat_id_to_name: dict[uuid.UUID, str],
    now: datetime,
) -> tuple[list[_LegPreview], int | None]:
    """If the version is in no **source** catalog for a channel step, return ``([], None)``."""
    steps = sorted(ch.steps, key=lambda s: s.step_order)
    if not steps:
        return ([], None)
    i0: int | None = None
    for i, step in enumerate(steps):
        if step.source_catalog_id in link_by_cat_id:
            i0 = i
            break
    if i0 is None:
        return ([], None)
    first_link = link_by_cat_id[steps[i0].source_catalog_id]
    t_cursor = _as_utc(first_link.entered_at)
    legs_out: list[_LegPreview] = []
    for j in range(i0, len(steps)):
        s = steps[j]
        src = cat_id_to_name.get(s.source_catalog_id, "source")
        tgt = cat_id_to_name.get(s.target_catalog_id, "target")
        dwell = s.dwell_days
        clock_start_utc = _as_utc(t_cursor)
        promote_at = t_cursor + timedelta(days=dwell) if dwell and dwell > 0 else t_cursor
        pa = _as_utc(promote_at)
        if pa <= now:
            st = "eligible"
            rem = 0
        else:
            st = "waiting"
            rem = _days_remaining_ceil(now, pa)
        legs_out.append(
            _LegPreview(
                step_order=s.step_order,
                source_catalog_name=src,
                target_catalog_name=tgt,
                dwell_days=dwell,
                promote_at=pa,
                days_remaining=rem,
                status=st,
                dwell_clock_start_at=clock_start_utc,
            )
        )
        t_cursor = pa
    return (legs_out, i0)


async def _pkginfo_catalog_memberships(session: AsyncSession, pkg_id: uuid.UUID) -> list[dict[str, str | datetime]]:
    row_result = await session.execute(
        select(PkgInfoCatalog, Catalog)
        .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
        .where(PkgInfoCatalog.pkg_info_id == pkg_id)
    )
    rows = row_result.all()
    out: list[dict[str, str | datetime]] = [{"catalog_name": r[1].name, "entered_at": r[0].entered_at} for r in rows]
    out.sort(key=lambda m: str(m["catalog_name"]).casefold())
    return out


async def build_pkginfo_channel_promotion_status(session: AsyncSession, pkg: PkgInfo) -> dict:
    """Preview scheduled promotions from ``munki_pkginfo_catalog`` + channel steps (no recipe rows)."""
    catalog_memberships = await _pkginfo_catalog_memberships(session, pkg.id)
    if not pkg.auto_promote and not pkg.promotion_channel_id:
        return {
            "active": False,
            "summary": (
                "This version has no automatic channel promotion. It is not marked for "
                "auto-promote or has no channel on the software record. Re-run import "
                "from AutoPkg, or set these on the software page."
            ),
            "auto_promote": bool(pkg.auto_promote),
            "promotion_channel_id": pkg.promotion_channel_id,
            "channel_name": None,
            "current_catalog_summary": ", ".join(c.name for c in (pkg.catalogs or [])) or "—",
            "catalog_memberships": catalog_memberships,
            "legs": [],
        }
    if not pkg.promotion_channel_id:
        return {
            "active": False,
            "summary": (
                "Auto-promote is on but no promotion channel is set. Choose a channel "
                "on this software version or re-import from a recipe with a channel "
                "(or a workflow default)."
            ),
            "auto_promote": bool(pkg.auto_promote),
            "promotion_channel_id": None,
            "channel_name": None,
            "current_catalog_summary": ", ".join(c.name for c in (pkg.catalogs or [])) or "—",
            "catalog_memberships": catalog_memberships,
            "legs": [],
        }
    if not pkg.auto_promote:
        ch_off = await session.get(PromotionChannel, pkg.promotion_channel_id)
        return {
            "active": True,
            "summary": (
                "A promotion channel is set but auto-promote is off for this version; "
                "it will not move automatically. Turn on auto-promote to use the channel."
            ),
            "auto_promote": False,
            "promotion_channel_id": pkg.promotion_channel_id,
            "channel_name": ch_off.name if ch_off else None,
            "current_catalog_summary": ", ".join(c.name for c in (pkg.catalogs or [])) or "—",
            "catalog_memberships": catalog_memberships,
            "legs": [],
        }
    ch = await session.get(
        PromotionChannel,
        pkg.promotion_channel_id,
        options=(selectinload(PromotionChannel.steps),),
    )
    if not ch:
        return {
            "active": False,
            "summary": "The channel selected for this version no longer exists. Pick another channel on this page.",
            "auto_promote": bool(pkg.auto_promote),
            "promotion_channel_id": pkg.promotion_channel_id,
            "channel_name": None,
            "current_catalog_summary": ", ".join(c.name for c in (pkg.catalogs or [])) or "—",
            "catalog_memberships": catalog_memberships,
            "legs": [],
        }
    steps = sorted(ch.steps, key=lambda s: s.step_order)
    if not steps:
        return {
            "active": True,
            "summary": f"Channel “{ch.name}” has no steps yet.",
            "auto_promote": True,
            "promotion_channel_id": ch.id,
            "channel_name": ch.name,
            "current_catalog_summary": ", ".join(c.name for c in (pkg.catalogs or [])) or "—",
            "catalog_memberships": catalog_memberships,
            "legs": [],
        }

    row_result = await session.execute(
        select(PkgInfoCatalog, Catalog)
        .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
        .where(PkgInfoCatalog.pkg_info_id == pkg.id)
    )
    rows = row_result.all()
    link_by_cat_id: dict[uuid.UUID, PkgInfoCatalog] = {r[0].catalog_id: r[0] for r in rows}
    cat_id_to_name: dict[uuid.UUID, str] = {r[0].catalog_id: r[1].name for r in rows}
    for s in steps:
        if s.source_catalog_id not in cat_id_to_name:
            c = await session.get(Catalog, s.source_catalog_id)
            if c:
                cat_id_to_name[s.source_catalog_id] = c.name
        if s.target_catalog_id not in cat_id_to_name:
            c2 = await session.get(Catalog, s.target_catalog_id)
            if c2:
                cat_id_to_name[s.target_catalog_id] = c2.name
    now = datetime.now(UTC)
    cur_names = ", ".join(cat_id_to_name.get(r[0].catalog_id, "?") for r in rows) or "—"
    legs_out, i0 = _build_leg_previews(ch, link_by_cat_id, cat_id_to_name, now)
    if i0 is None:
        return {
            "active": True,
            "summary": (
                "This version is not in any of this channel’s source catalogs, so the "
                f"dwell timer is not running. Current catalogs: {cur_names}. When it is "
                "added to the first source catalog in the channel, scheduled dates "
                "appear here."
            ),
            "auto_promote": True,
            "promotion_channel_id": ch.id,
            "channel_name": ch.name,
            "current_catalog_summary": cur_names,
            "catalog_memberships": catalog_memberships,
            "legs": [],
        }
    first = steps[i0]
    src0 = cat_id_to_name.get(first.source_catalog_id, "source")
    if not legs_out:
        summary = f"Channel {ch.name!r} has no leg preview (unexpected)."
    else:
        bits: list[str] = []
        for leg in legs_out[:3]:
            if leg.status == "waiting":
                bits.append(
                    f"to {leg.target_catalog_name} in {leg.days_remaining} day(s) "
                    f"(dwell {leg.dwell_days}d, from {leg.source_catalog_name})"
                )
            else:
                bits.append(
                    f"to {leg.target_catalog_name} eligible on the next promotion run (dwell {leg.dwell_days}d met)"
                )
        summary = (
            f"Auto-promote is on, channel {ch.name!r}. You are in {src0!r} for a channel step. Upcoming: "
            + "; ".join(bits)
        )

    return {
        "active": True,
        "summary": summary,
        "auto_promote": True,
        "promotion_channel_id": ch.id,
        "channel_name": ch.name,
        "current_catalog_summary": cur_names,
        "catalog_memberships": catalog_memberships,
        "legs": [
            {
                "step_order": leg.step_order,
                "source_catalog_name": leg.source_catalog_name,
                "target_catalog_name": leg.target_catalog_name,
                "dwell_days": leg.dwell_days,
                "promote_at": leg.promote_at,
                "days_remaining": leg.days_remaining,
                "status": leg.status,
                "dwell_clock_start_at": leg.dwell_clock_start_at,
            }
            for leg in legs_out
        ],
    }


async def list_channel_promotion_queue_items(session: AsyncSession, *, limit: int = 30) -> list[dict]:
    """PkgInfo rows on a channel with auto-promote, in a **source** catalog (dwell/queue path)."""
    result = await session.execute(
        select(PkgInfo).where(
            PkgInfo.is_deleted.is_(False),
            PkgInfo.auto_promote.is_(True),
            PkgInfo.promotion_channel_id.isnot(None),
        )
    )
    candidates: list[PkgInfo] = list(result.scalars().all())
    if not candidates:
        return []

    ch_ids = {p.promotion_channel_id for p in candidates if p.promotion_channel_id}
    ch_res = await session.execute(
        select(PromotionChannel).options(selectinload(PromotionChannel.steps)).where(PromotionChannel.id.in_(ch_ids))
    )
    ch_by_id: dict[uuid.UUID, PromotionChannel] = {c.id: c for c in ch_res.scalars()}

    pkg_ids = [p.id for p in candidates]
    link_res = await session.execute(
        select(PkgInfoCatalog, Catalog)
        .join(Catalog, PkgInfoCatalog.catalog_id == Catalog.id)
        .where(PkgInfoCatalog.pkg_info_id.in_(pkg_ids))
    )
    links_by_pkg: dict[uuid.UUID, dict[uuid.UUID, PkgInfoCatalog]] = {}
    all_cat_ids: set[uuid.UUID] = set()
    for pic, c in link_res.all():
        links_by_pkg.setdefault(pic.pkg_info_id, {})[c.id] = pic
        all_cat_ids.add(c.id)
    for ch in ch_by_id.values():
        for s in ch.steps or []:
            all_cat_ids.add(s.source_catalog_id)
            all_cat_ids.add(s.target_catalog_id)

    if all_cat_ids:
        cat_res = await session.execute(select(Catalog).where(Catalog.id.in_(all_cat_ids)))
        global_cat: dict[uuid.UUID, str] = {c.id: c.name for c in cat_res.scalars().all()}
    else:
        global_cat = {}

    now = datetime.now(UTC)
    out: list[dict] = []
    for pkg in candidates:
        ch = ch_by_id.get(pkg.promotion_channel_id) if pkg.promotion_channel_id else None
        if not ch or not ch.steps:
            continue
        link_by = links_by_pkg.get(pkg.id) or {}
        if not link_by:
            continue
        legs_out, _i0 = _build_leg_previews(ch, link_by, global_cat, now)
        if _i0 is None or not legs_out:
            continue
        first_waiting = next((L for L in legs_out if L.status == "waiting"), None)
        focus = first_waiting or next((L for L in legs_out if L.status == "eligible"), None)
        if focus is None:
            continue
        out.append(
            {
                "id": pkg.id,
                "name": pkg.name,
                "version": pkg.version,
                "display_name": pkg.display_name,
                "channel_name": ch.name,
                "next_source_catalog": focus.source_catalog_name,
                "next_target_catalog": focus.target_catalog_name,
                "leg_status": focus.status,
                "days_remaining": focus.days_remaining,
                "promote_at": focus.promote_at,
            }
        )

    def _sort_key(d: dict) -> tuple:
        if d.get("leg_status") == "waiting":
            return (0, d.get("promote_at"), d.get("name") or "", d.get("version") or "")
        return (1, d.get("name") or "", d.get("version") or "")

    out.sort(key=_sort_key)
    return out[: max(0, min(limit, 200))]


async def run_all_auto_promotions(session: AsyncSession) -> dict:
    """Legacy per-title rules + channel tick (scheduler entry point)."""
    from automunki.services.shard_rollout import run_production_shard_tick

    legacy = await check_auto_promotions(session)
    channel = await run_promotion_channel_tick(session)
    shard = await run_production_shard_tick(session)
    return {"legacy_auto_time": legacy, "promotion_channels": channel, "production_shard": shard}
