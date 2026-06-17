"""Insights tool registry: declarative definitions + execution dispatch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.services.insights import handlers

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class InsightTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


def _schema(*, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


INSIGHT_TOOLS: dict[str, InsightTool] = {
    "get_fleet_compliance": InsightTool(
        name="get_fleet_compliance",
        description=(
            "Fleet check-in compliance: total machines, count checked in within 7 days, "
            "count stale over 30 days, and compliance percentage."
        ),
        parameters=_schema(properties={}),
        handler=handlers.get_fleet_compliance,
    ),
    "list_stale_machines": InsightTool(
        name="list_stale_machines",
        description=(
            "List machines that have not checked in within a rolling window. "
            "Use days=30 for 'last month'. Returns hostnames, serials, manifests, last check-in."
        ),
        parameters=_schema(
            properties={
                "days": {
                    "type": "integer",
                    "description": "Rolling stale threshold in days (default 30).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default 200).",
                },
            },
        ),
        handler=handlers.list_stale_machines,
    ),
    "count_autopromote_enabled": InsightTool(
        name="count_autopromote_enabled",
        description=(
            "Count distinct software titles with auto-promote enabled on pkginfo. "
            "This is how many apps are configured for auto-promotion, not the active queue."
        ),
        parameters=_schema(properties={}),
        handler=handlers.count_autopromote_enabled,
    ),
    "list_autopromote_queue": InsightTool(
        name="list_autopromote_queue",
        description=(
            "List pkginfo versions actively in a promotion channel step (the promotion queue). "
            "Different from count_autopromote_enabled which counts all titles with the flag on."
        ),
        parameters=_schema(
            properties={
                "limit": {
                    "type": "integer",
                    "description": "Max queue items to return (default 50).",
                },
            },
        ),
        handler=handlers.list_autopromote_queue,
    ),
    "resolve_software_identity": InsightTool(
        name="resolve_software_identity",
        description=(
            "Resolve a colloquial software name to Munki pkginfo item names, display names "
            "(e.g. Munki → Managed Software Center), bundle IDs, and fleet inventory labels. "
            "Call this when the user mentions an app by nickname before version queries."
        ),
        parameters=_schema(
            properties={
                "query": {
                    "type": "string",
                    "description": "Free-text software name from the user (preferred).",
                },
                "item_name": {"type": "string", "description": "Munki pkginfo item name."},
                "app_name": {"type": "string", "description": "Application display name."},
                "bundle_id": {"type": "string", "description": "macOS bundle identifier."},
            },
        ),
        handler=handlers.resolve_software_identity_handler,
    ),
    "get_installed_software_version_distribution": InsightTool(
        name="get_installed_software_version_distribution",
        description=(
            "Version histogram across the fleet from client application inventory. "
            "Prefer the query parameter for fuzzy names (e.g. munki, chrome). "
            "Automatically maps pkginfo display names to inventory names "
            "(Munki item → Managed Software Center in inventory)."
        ),
        parameters=_schema(
            properties={
                "query": {
                    "type": "string",
                    "description": "Free-text software name; resolves aliases and display names.",
                },
                "item_name": {"type": "string", "description": "Munki pkginfo item name."},
                "app_name": {"type": "string", "description": "Application display name from inventory."},
                "bundle_id": {"type": "string", "description": "macOS bundle identifier."},
            },
        ),
        handler=handlers.get_installed_software_version_distribution,
    ),
    "get_catalog_latest_version": InsightTool(
        name="get_catalog_latest_version",
        description=(
            "Latest non-deleted pkginfo version for software. Accepts fuzzy query "
            "(e.g. munki, Managed Software Center) or exact item_name."
        ),
        parameters=_schema(
            properties={
                "query": {
                    "type": "string",
                    "description": "Free-text software name; resolves to pkginfo item.",
                },
                "item_name": {"type": "string", "description": "Exact Munki pkginfo item name."},
            },
        ),
        handler=handlers.get_catalog_latest_version,
    ),
    "compare_fleet_version_to_latest": InsightTool(
        name="compare_fleet_version_to_latest",
        description=(
            "Compare fleet-installed versions to the latest catalog version. "
            "Use query for fuzzy names (munki, chrome). Resolves display vs inventory names automatically."
        ),
        parameters=_schema(
            properties={
                "query": {
                    "type": "string",
                    "description": "Free-text software name; resolves aliases and display names.",
                },
                "item_name": {"type": "string", "description": "Munki pkginfo item name."},
                "app_name": {"type": "string", "description": "Application display name from inventory."},
                "bundle_id": {"type": "string", "description": "macOS bundle identifier."},
            },
        ),
        handler=handlers.compare_fleet_version_to_latest,
    ),
}


def gemini_function_declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=types.Schema(**tool.parameters),
        )
        for tool in INSIGHT_TOOLS.values()
    ]


async def execute_tool(session: AsyncSession, name: str, args: dict[str, Any]) -> dict[str, Any]:
    tool = INSIGHT_TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await tool.handler(session, **args)
    except TypeError as exc:
        return {"error": f"Invalid arguments for {name}: {exc}"}


def summarize_tool_result(name: str, result: dict[str, Any]) -> str:
    if "error" in result:
        return str(result["error"])
    if name == "get_fleet_compliance":
        return (
            f"{result.get('total_machines')} machines; "
            f"{result.get('checked_in_last_7_days')} active (7d); "
            f"{result.get('stale_over_30_days')} stale (30d)"
        )
    if name == "list_stale_machines":
        return f"{result.get('total_stale')} stale machines (>{result.get('days')}d)"
    if name == "count_autopromote_enabled":
        return f"{result.get('distinct_software_titles')} titles with auto-promote enabled"
    if name == "list_autopromote_queue":
        return f"{result.get('queue_count')} items in promotion queue"
    if name == "compare_fleet_version_to_latest":
        return (
            f"{result.get('percentage_on_latest')}% on latest "
            f"({result.get('machines_on_latest')}/{result.get('machines_with_app')})"
        )
    if name == "get_catalog_latest_version":
        return f"Latest {result.get('item_name')}: {result.get('latest_version')}"
    if name == "resolve_software_identity":
        return f"Resolved to {result.get('canonical_item_name')} ({len(result.get('matchers') or [])} matchers)"
    if name == "get_installed_software_version_distribution":
        return f"{result.get('machines_with_app')} machines with app installed"
    return "ok"


def extract_table(result: dict[str, Any]) -> dict[str, Any] | None:
    table = result.get("table")
    if isinstance(table, dict) and table.get("columns") and table.get("rows"):
        return table
    return None
