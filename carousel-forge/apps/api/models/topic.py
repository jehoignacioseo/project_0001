"""TopicBrief — 어떤 입력이든 수렴시킨 정규화된 주제."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel

from .base import JsonField, PrimaryKey, TimestampField
from .enums import TopicInputType


class TopicBrief(SQLModel, table=True):
    __tablename__ = "topic_brief"

    id: str = PrimaryKey()
    account_id: str = Field(foreign_key="account.id", index=True)
    raw_input_type: TopicInputType
    raw_payload: str | None = Field(default=None)

    #: schemas/topic.schema.json 계약
    normalized: dict[str, Any] = JsonField()

    #: TrendScout(A3)가 먼저 제안한 주제인가
    proposed_by_system: bool = Field(default=False)
    trend_score: float | None = Field(default=None)
    created_at: datetime = TimestampField()
