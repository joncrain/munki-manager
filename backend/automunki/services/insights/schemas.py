"""Pydantic models for the insights API."""

from pydantic import BaseModel, Field


class InsightsHistoryMessage(BaseModel):
    role: str = Field(description="user or assistant")
    content: str


class InsightsQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[InsightsHistoryMessage] = Field(default_factory=list)


class InsightsToolUsed(BaseModel):
    name: str
    args: dict
    summary: str


class InsightsTableData(BaseModel):
    columns: list[str]
    rows: list[list[str | int | float | None]]


class InsightsQueryResponse(BaseModel):
    answer: str
    tools_used: list[InsightsToolUsed] = Field(default_factory=list)
    data: InsightsTableData | None = None
