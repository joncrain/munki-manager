"""Gemini tool-calling agent for admin insights."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.core.config import settings
from automunki.services.audit import create_audit_entry
from automunki.services.insights.schemas import (
    InsightsQueryResponse,
    InsightsTableData,
    InsightsToolUsed,
)
from automunki.services.insights.tools import (
    INSIGHT_TOOLS,
    execute_tool,
    extract_table,
    gemini_function_declarations,
    summarize_tool_result,
)

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an operations assistant for Munki Manager, a macOS software deployment platform.

You help administrators answer questions about:
- Fleet client check-ins and compliance
- Installed application versions reported by managed Macs
- Munki pkginfo catalog versions
- Auto-promote configuration and the active promotion queue

Rules:
- Always call tools to fetch data; never invent counts or percentages.
- Distinguish auto-promote *enabled* (count_autopromote_enabled) from the active
  *promotion queue* (list_autopromote_queue).
- For application version questions, prefer compare_fleet_version_to_latest when the
  user asks about "latest" or a percentage.
- For Chrome, try query=chrome or query=GoogleChrome.
- For Munki client app: query=munki resolves item name Munki, display name Managed Software Center,
  and inventory bundle_id ManagedSoftwareCenter. Call resolve_software_identity when unsure.
- Prefer the ``query`` parameter on software tools for fuzzy user wording.
- "Last month" for check-ins means a rolling 30-day stale window (list_stale_machines with days=30).
- Answer concisely in plain language. Include key numbers from tool results.
- If data is truncated, mention that more rows exist.
"""


class InsightsNotConfiguredError(Exception):
    """Raised when insights is disabled or missing API credentials."""


def insights_is_configured() -> bool:
    return bool(settings.insights_enabled and settings.gemini_api_key.strip())


def _build_client() -> genai.Client:
    if not insights_is_configured():
        raise InsightsNotConfiguredError("AI Insights is not configured. Set INSIGHTS_ENABLED=true and GEMINI_API_KEY.")
    return genai.Client(api_key=settings.gemini_api_key.strip())


def _contents_from_history(
    question: str,
    history: list[dict[str, str]],
) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in history[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append(types.Content(role=gemini_role, parts=[types.Part(text=content)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    return contents


def _part_function_call(part: types.Part) -> types.FunctionCall | None:
    fc = getattr(part, "function_call", None)
    if fc is not None:
        return fc
    return None


def _extract_text(response: types.GenerateContentResponse) -> str:
    if not response.candidates:
        return ""
    parts = response.candidates[0].content.parts if response.candidates[0].content else []
    texts: list[str] = []
    for part in parts:
        if part.text:
            texts.append(part.text)
    return "\n".join(texts).strip()


def _extract_chunk_text(chunk: types.GenerateContentResponse) -> str:
    if not chunk.candidates:
        return ""
    content = chunk.candidates[0].content
    if not content or not content.parts:
        return ""
    return "".join(part.text for part in content.parts if part.text)


async def _generate_content(
    client: genai.Client,
    *,
    contents: list[types.Content],
    tools: list[types.Tool] | None = None,
) -> types.GenerateContentResponse:
    config_kwargs: dict[str, Any] = {
        "system_instruction": SYSTEM_PROMPT,
    }
    if tools:
        config_kwargs["tools"] = tools

    def _call() -> types.GenerateContentResponse:
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    return await asyncio.to_thread(_call)


async def _stream_content_chunks(
    client: genai.Client,
    *,
    contents: list[types.Content],
) -> AsyncIterator[str]:
    """Yield text deltas from Gemini's sync streaming iterator in a worker thread."""
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
    loop = asyncio.get_running_loop()
    q: queue.Queue[str | None] = queue.Queue()

    def _producer() -> None:
        try:
            stream = client.models.generate_content_stream(
                model=settings.gemini_model,
                contents=contents,
                config=config,
            )
            for chunk in stream:
                text = _extract_chunk_text(chunk)
                if text:
                    loop.call_soon_threadsafe(q.put_nowait, text)
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        item = await asyncio.to_thread(q.get)
        if item is None:
            break
        yield item


async def _run_tool_rounds(
    session: AsyncSession,
    client: genai.Client,
    *,
    contents: list[types.Content],
    tools: list[types.Tool],
    on_tool_start: Any | None = None,
    on_tool_done: Any | None = None,
) -> tuple[list[types.Content], list[InsightsToolUsed], dict[str, Any] | None, str | None]:
    """Execute tool-calling rounds. Returns contents, tools_used, last_table, immediate_answer."""
    tools_used: list[InsightsToolUsed] = []
    last_table: dict[str, Any] | None = None

    for round_idx in range(settings.insights_max_tool_rounds):
        response = await _generate_content(client, contents=contents, tools=tools)
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            break

        function_calls: list[tuple[str, dict[str, Any]]] = []
        for part in candidate.content.parts or []:
            fc = _part_function_call(part)
            if fc and fc.name:
                args = dict(fc.args) if fc.args else {}
                function_calls.append((fc.name, args))

        if not function_calls:
            answer = _extract_text(response) or None
            return contents, tools_used, last_table, answer

        contents.append(candidate.content)
        response_parts: list[types.Part] = []

        for name, args in function_calls:
            if on_tool_start is not None:
                await on_tool_start(name, args)

            if name not in INSIGHT_TOOLS:
                result = {"error": f"Unknown tool: {name}"}
            else:
                result = await execute_tool(session, name, args)

            summary = summarize_tool_result(name, result)
            tool_row = InsightsToolUsed(name=name, args=args, summary=summary)
            tools_used.append(tool_row)

            table = extract_table(result)
            if table:
                last_table = table

            if on_tool_done is not None:
                await on_tool_done(tool_row, table)

            response_parts.append(
                types.Part.from_function_response(
                    name=name,
                    response={"result": result},
                )
            )
            logger.info("insights_tool_call", tool=name, args=args, round=round_idx)

        contents.append(types.Content(role="user", parts=response_parts))

    return contents, tools_used, last_table, None


def _table_from_raw(table: dict[str, Any] | None) -> InsightsTableData | None:
    if not table:
        return None
    return InsightsTableData(
        columns=[str(c) for c in table["columns"]],
        rows=table["rows"],
    )


async def _audit_query(
    session: AsyncSession,
    *,
    question: str,
    tools_used: list[InsightsToolUsed],
    user_id: uuid.UUID | None,
    user_email: str | None,
) -> None:
    await create_audit_entry(
        session,
        action="insights_query",
        entity_type="insights",
        entity_id="query",
        entity_name=question[:200],
        user_id=user_id,
        user_email=user_email,
        after_snapshot={
            "question": question,
            "tools": [t.model_dump() for t in tools_used],
        },
        notes=f"AI insights query ({len(tools_used)} tool calls)",
    )
    await session.commit()


async def run_insights_query(
    session: AsyncSession,
    *,
    question: str,
    history: list[dict[str, str]] | None = None,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
) -> InsightsQueryResponse:
    client = _build_client()
    contents = _contents_from_history(question, history or [])
    tools = [types.Tool(function_declarations=gemini_function_declarations())]

    contents, tools_used, last_table, immediate_answer = await _run_tool_rounds(
        session, client, contents=contents, tools=tools
    )

    if immediate_answer is not None:
        answer = immediate_answer or "I couldn't generate an answer."
        await _audit_query(
            session,
            question=question,
            tools_used=tools_used,
            user_id=user_id,
            user_email=user_email,
        )
        return InsightsQueryResponse(
            answer=answer,
            tools_used=tools_used,
            data=_table_from_raw(last_table),
        )

    final = await _generate_content(client, contents=contents, tools=None)
    answer = _extract_text(final) or "I couldn't generate an answer from the available data."

    await _audit_query(
        session,
        question=question,
        tools_used=tools_used,
        user_id=user_id,
        user_email=user_email,
    )

    return InsightsQueryResponse(
        answer=answer,
        tools_used=tools_used,
        data=_table_from_raw(last_table),
    )


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def stream_insights_query(
    session: AsyncSession,
    *,
    question: str,
    history: list[dict[str, str]] | None = None,
    user_id: uuid.UUID | None = None,
    user_email: str | None = None,
) -> AsyncIterator[str]:
    """Server-sent events for tool progress, table data, and streamed answer text."""
    try:
        client = _build_client()
    except InsightsNotConfiguredError as exc:
        yield _sse_event({"type": "error", "message": str(exc)})
        return

    contents = _contents_from_history(question, history or [])
    tools = [types.Tool(function_declarations=gemini_function_declarations())]
    tools_used: list[InsightsToolUsed] = []
    last_table: dict[str, Any] | None = None
    pending_events: list[str] = []

    async def _tool_start(name: str, args: dict[str, Any]) -> None:
        pending_events.append(
            _sse_event({"type": "status", "phase": "tool", "message": f"Running {name}…", "name": name, "args": args})
        )

    async def _tool_done(tool_row: InsightsToolUsed, table: dict[str, Any] | None) -> None:
        pending_events.append(
            _sse_event(
                {
                    "type": "tool",
                    "name": tool_row.name,
                    "args": tool_row.args,
                    "summary": tool_row.summary,
                }
            )
        )
        if table:
            pending_events.append(_sse_event({"type": "data", "data": table}))

    contents, tools_used, last_table, immediate_answer = await _run_tool_rounds(
        session,
        client,
        contents=contents,
        tools=tools,
        on_tool_start=_tool_start,
        on_tool_done=_tool_done,
    )

    for event in pending_events:
        yield event

    if immediate_answer is not None:
        answer = immediate_answer or "I couldn't generate an answer."
        yield _sse_event({"type": "text-delta", "delta": answer})
        await _audit_query(
            session,
            question=question,
            tools_used=tools_used,
            user_id=user_id,
            user_email=user_email,
        )
        yield _sse_event(
            {
                "type": "done",
                "answer": answer,
                "tools_used": [t.model_dump() for t in tools_used],
                "data": last_table,
            }
        )
        return

    yield _sse_event({"type": "status", "phase": "answer", "message": "Generating answer…"})

    answer_parts: list[str] = []
    async for delta in _stream_content_chunks(client, contents=contents):
        answer_parts.append(delta)
        yield _sse_event({"type": "text-delta", "delta": delta})

    answer = "".join(answer_parts).strip() or "I couldn't generate an answer from the available data."

    await _audit_query(
        session,
        question=question,
        tools_used=tools_used,
        user_id=user_id,
        user_email=user_email,
    )

    yield _sse_event(
        {
            "type": "done",
            "answer": answer,
            "tools_used": [t.model_dump() for t in tools_used],
            "data": last_table,
        }
    )
