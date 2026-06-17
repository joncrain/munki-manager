"""Tests for the insights Gemini agent (mocked)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import types

from automunki.services.insights.agent import (
    InsightsNotConfiguredError,
    insights_is_configured,
    run_insights_query,
)


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("automunki.services.insights.agent.settings.insights_enabled", True)
    monkeypatch.setattr("automunki.services.insights.agent.settings.gemini_api_key", "test-key")
    monkeypatch.setattr("automunki.services.insights.agent.settings.gemini_model", "gemini-2.0-flash")
    monkeypatch.setattr("automunki.services.insights.agent.settings.insights_max_tool_rounds", 3)


def test_insights_not_configured_when_disabled(monkeypatch):
    monkeypatch.setattr("automunki.services.insights.agent.settings.insights_enabled", False)
    monkeypatch.setattr("automunki.services.insights.agent.settings.gemini_api_key", "")
    assert insights_is_configured() is False


@pytest.mark.asyncio
async def test_run_insights_query_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr("automunki.services.insights.agent.settings.insights_enabled", False)
    monkeypatch.setattr("automunki.services.insights.agent.settings.gemini_api_key", "")
    session = AsyncMock()
    with pytest.raises(InsightsNotConfiguredError):
        await run_insights_query(session, question="How many machines?")


@pytest.mark.asyncio
async def test_run_insights_query_direct_answer(mock_settings, monkeypatch):
    session = AsyncMock()
    session.commit = AsyncMock()

    text_part = types.Part(text="There are 42 machines in the fleet.")
    final_content = types.Content(role="model", parts=[text_part])
    final_response = types.GenerateContentResponse(
        candidates=[types.Candidate(content=final_content, finish_reason=types.FinishReason.STOP)]
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = final_response

    monkeypatch.setattr("automunki.services.insights.agent._build_client", lambda: mock_client)
    monkeypatch.setattr(
        "automunki.services.insights.agent.create_audit_entry",
        AsyncMock(),
    )

    result = await run_insights_query(
        session,
        question="How many machines?",
        user_id=uuid.uuid4(),
        user_email="admin@example.com",
    )

    assert "42 machines" in result.answer
    assert result.tools_used == []
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_insights_query_with_tool_call(mock_settings, monkeypatch):
    session = AsyncMock()
    session.commit = AsyncMock()

    fc_part = types.Part(
        function_call=types.FunctionCall(name="get_fleet_compliance", args={}),
    )
    tool_response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[fc_part]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )

    final_part = types.Part(text="You have 100 machines; 80 checked in recently.")
    final_response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[final_part]),
                finish_reason=types.FinishReason.STOP,
            )
        ]
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [tool_response, final_response]

    monkeypatch.setattr("automunki.services.insights.agent._build_client", lambda: mock_client)
    monkeypatch.setattr(
        "automunki.services.insights.agent.execute_tool",
        AsyncMock(
            return_value={
                "total_machines": 100,
                "checked_in_last_7_days": 80,
                "stale_over_30_days": 20,
                "compliance_percentage": 80.0,
            }
        ),
    )
    monkeypatch.setattr(
        "automunki.services.insights.agent.create_audit_entry",
        AsyncMock(),
    )

    result = await run_insights_query(session, question="Fleet compliance?")

    assert result.tools_used
    assert result.tools_used[0].name == "get_fleet_compliance"
    assert "100 machines" in result.answer or "80" in result.answer
