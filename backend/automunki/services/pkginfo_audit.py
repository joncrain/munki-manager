"""Helpers for pkginfo audit snapshots and change summaries."""

from __future__ import annotations

import copy
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.munki import Catalog, PkgInfoCatalog


async def fetch_pkg_catalog_names(session: AsyncSession, pkg_id: uuid.UUID) -> list[str]:
    """Catalog names for a pkginfo row, read from the association table (not ORM cache)."""
    result = await session.execute(
        select(Catalog.name)
        .join(PkgInfoCatalog, PkgInfoCatalog.catalog_id == Catalog.id)
        .where(PkgInfoCatalog.pkg_info_id == pkg_id)
        .order_by(Catalog.name)
    )
    return list(result.scalars().all())


def snapshot_copy(snapshot: dict) -> dict:
    """Detach nested JSONB values so audit before rows cannot mutate after apply."""
    return copy.deepcopy(snapshot)


def audit_values_equal(before: object, after: object) -> bool:
    if isinstance(before, (list, dict)) or isinstance(after, (list, dict)):
        return json.dumps(before, sort_keys=True, default=str) == json.dumps(after, sort_keys=True, default=str)
    return before == after


def build_audit_field_changes(before: dict, update_data: dict) -> dict:
    """Map each updated field to ``{before, after}`` pairs, omitting no-ops."""
    changes: dict = {}
    for field, after in update_data.items():
        before_val = before.get(field)
        if audit_values_equal(before_val, after):
            continue
        changes[field] = {"before": before_val, "after": after}
    return changes
