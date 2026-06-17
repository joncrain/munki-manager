"""Resolve colloquial software names to Munki pkginfo + fleet inventory matchers."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.client import ClientMachine
from automunki.models.munki import PkgInfo

# Colloquial terms → strings that appear in pkginfo or client inventory.
# Keys are normalized (alnum-only, lowercased).
KNOWN_SOFTWARE_ALIASES: dict[str, list[str]] = {
    "munki": ["Munki", "Managed Software Center", "ManagedSoftwareCenter", "munkitools"],
    "munkitools": ["Munki", "Managed Software Center", "ManagedSoftwareCenter", "munkitools"],
    "managedsoftwarecenter": ["Munki", "Managed Software Center", "ManagedSoftwareCenter"],
    "managedsoftware": ["Munki", "Managed Software Center", "ManagedSoftwareCenter"],
    "googlechrome": ["GoogleChrome", "Google Chrome", "com.google.Chrome"],
    "chrome": ["GoogleChrome", "Google Chrome", "com.google.Chrome"],
}


def _normalize_label(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _tokenize(value: str) -> set[str]:
    parts = re.split(r"[^a-zA-Z0-9]+", value.lower())
    return {p for p in parts if len(p) >= 2}


def _labels_from_terms(terms: list[str]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not term or not term.strip():
            continue
        raw = term.strip()
        norm = _normalize_label(raw)
        for candidate in (raw, norm):
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                labels.append(candidate)
        for alias in KNOWN_SOFTWARE_ALIASES.get(norm, []):
            key = alias.lower()
            if key not in seen:
                seen.add(key)
                labels.append(alias)
    return labels


def _bundle_ids_from_installs(installs: object) -> list[str]:
    if not isinstance(installs, list):
        return []
    out: list[str] = []
    for item in installs:
        if not isinstance(item, dict):
            continue
        bid = item.get("CFBundleIdentifier") or item.get("bundleid") or item.get("bundleID")
        if isinstance(bid, str) and bid.strip():
            out.append(bid.strip())
    return out


def software_entry_matches(entry: dict, matchers: list[str]) -> bool:
    """True when an inventory row matches any resolved label."""
    if not matchers:
        return False

    name = str(entry.get("name") or "")
    bid = str(entry.get("bundle_id") or "")
    name_norm = _normalize_label(name)
    bid_norm = _normalize_label(bid)
    name_tokens = _tokenize(name)
    bid_tokens = _tokenize(bid)

    for matcher in matchers:
        m = matcher.strip()
        if not m:
            continue
        m_lower = m.lower()
        m_norm = _normalize_label(m)
        m_tokens = _tokenize(m)

        if m_lower == name.lower() or m_lower == bid.lower():
            return True
        if m_norm and (m_norm == name_norm or m_norm == bid_norm):
            return True
        if m_norm and len(m_norm) >= 4 and (m_norm in name_norm or m_norm in bid_norm):
            return True
        if m_norm and len(m_norm) >= 4 and (name_norm in m_norm or bid_norm in m_norm):
            return True
        if m_tokens and (m_tokens <= name_tokens or m_tokens <= bid_tokens):
            return True
        if m.replace(" ", "") == name.replace(" ", ""):
            return True

    return False


async def _pkginfo_candidates(session: AsyncSession, terms: list[str]) -> list[PkgInfo]:
    labels = _labels_from_terms(terms)
    if not labels:
        return []

    conditions = []
    for label in labels:
        pat = f"%{label}%"
        conditions.append(PkgInfo.name.ilike(pat))
        conditions.append(PkgInfo.display_name.ilike(pat))

    result = await session.execute(
        select(PkgInfo).where(PkgInfo.is_deleted.is_(False)).where(or_(*conditions)).limit(40)
    )
    rows = list(result.scalars().all())

    # Rank: prefer rows whose name or display_name best matches the primary query term.
    primary = _normalize_label(terms[0]) if terms else ""

    def _rank(pkg: PkgInfo) -> tuple[int, str]:
        name_norm = _normalize_label(pkg.name)
        display_norm = _normalize_label(pkg.display_name or "")
        score = 0
        if primary and primary == name_norm:
            score += 100
        if primary and primary in name_norm:
            score += 40
        if primary and primary in display_norm:
            score += 30
        if primary and display_norm and primary in display_norm:
            score += 20
        return (-score, pkg.name)

    rows.sort(key=_rank)
    return rows


async def _fleet_inventory_labels(session: AsyncSession, terms: list[str]) -> list[str]:
    """Distinct inventory name/bundle_id values that loosely match ``terms``."""
    labels = _labels_from_terms(terms)
    if not labels:
        return []

    result = await session.execute(
        select(ClientMachine.installed_software).where(ClientMachine.installed_software.isnot(None)).limit(500)
    )
    found: list[str] = []
    seen: set[str] = set()

    for (installed_software,) in result.all():
        if not isinstance(installed_software, list):
            continue
        for entry in installed_software:
            if not isinstance(entry, dict):
                continue
            if not software_entry_matches(entry, labels):
                continue
            for key in ("name", "bundle_id"):
                val = entry.get(key)
                if isinstance(val, str) and val.strip():
                    k = val.strip().lower()
                    if k not in seen:
                        seen.add(k)
                        found.append(val.strip())
    return found


async def resolve_software_identity(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    app_name: str | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    """Map fuzzy user/software terms to pkginfo + inventory matchers."""
    terms: list[str] = []
    for raw in (query, item_name, app_name, bundle_id):
        if raw and raw.strip():
            terms.append(raw.strip())

    if not terms:
        return {"error": "Provide query, item_name, app_name, or bundle_id"}

    pkgs = await _pkginfo_candidates(session, terms)
    inventory_labels = await _fleet_inventory_labels(session, terms)

    matchers: list[str] = []
    seen: set[str] = set()

    def _add(label: str | None) -> None:
        if not label or not str(label).strip():
            return
        key = str(label).strip().lower()
        if key in seen:
            return
        seen.add(key)
        matchers.append(str(label).strip())

    for label in _labels_from_terms(terms):
        _add(label)
    for pkg in pkgs:
        _add(pkg.name)
        _add(pkg.display_name)
        for bid in _bundle_ids_from_installs(pkg.installs):
            _add(bid)
    for label in inventory_labels:
        _add(label)

    canonical_item_name = pkgs[0].name if pkgs else None
    if canonical_item_name is None:
        # Fall back to first alias or raw query when pkginfo is missing.
        for label in _labels_from_terms(terms):
            if label and not label.startswith("com."):
                canonical_item_name = label
                break

    pkginfo_matches = [
        {
            "item_name": p.name,
            "display_name": p.display_name,
            "bundle_ids": _bundle_ids_from_installs(p.installs),
        }
        for p in pkgs[:10]
    ]

    return {
        "query_terms": terms,
        "canonical_item_name": canonical_item_name,
        "matchers": matchers,
        "pkginfo_matches": pkginfo_matches,
        "inventory_names": inventory_labels[:20],
    }


async def expand_software_matchers(
    session: AsyncSession,
    *,
    query: str | None = None,
    item_name: str | None = None,
    app_name: str | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    """Resolve and return matchers plus canonical catalog item name."""
    resolved = await resolve_software_identity(
        session,
        query=query,
        item_name=item_name,
        app_name=app_name,
        bundle_id=bundle_id,
    )
    if "error" in resolved:
        return resolved
    return {
        "matchers": [m.lower() for m in resolved["matchers"]],
        "canonical_item_name": resolved.get("canonical_item_name"),
        "resolution": resolved,
    }
