"""Admin AI Insights API."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.api.deps import get_session
from automunki.services.insights.agent import (
    InsightsNotConfiguredError,
    run_insights_query,
    stream_insights_query,
)
from automunki.services.insights.schemas import InsightsQueryRequest, InsightsQueryResponse

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/query", response_model=InsightsQueryResponse)
async def query_insights(
    body: InsightsQueryRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> InsightsQueryResponse:
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    user_email = getattr(user, "email", None)

    try:
        return await run_insights_query(
            session,
            question=body.question.strip(),
            history=[m.model_dump() for m in body.history],
            user_id=user_id,
            user_email=user_email,
        )
    except InsightsNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/query/stream")
async def query_insights_stream(
    body: InsightsQueryRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    user_email = getattr(user, "email", None)

    async def event_stream():
        try:
            async for chunk in stream_insights_query(
                session,
                question=body.question.strip(),
                history=[m.model_dump() for m in body.history],
                user_id=user_id,
                user_email=user_email,
            ):
                yield chunk
        except InsightsNotConfiguredError as exc:
            yield f'data: {{"type":"error","message":{json.dumps(str(exc))}}}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
