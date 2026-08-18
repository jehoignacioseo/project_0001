"""FactCheck / GenerationLog — 검증과 폐기의 기록."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel

from .base import JsonField, PrimaryKey, TimestampField
from .enums import FactVerdict, GenerationVerdict, PipelineStage


class FactCheck(SQLModel, table=True):
    """주장 단위 검증 기록. 숫자·통계·연도·인용은 출처 링크가 없으면 통과하지 못한다."""

    __tablename__ = "fact_check"

    id: str = PrimaryKey()
    set_id: str = Field(foreign_key="carousel_set.id", index=True)
    slide_index: int | None = Field(default=None)
    claim: str
    verdict: FactVerdict = Field(index=True)
    #: [{title, url, publisher, accessed_at}, …]
    sources: list[dict[str, Any]] = JsonField(default_factory=list)
    checked_at: datetime = TimestampField()


class GenerationLog(SQLModel, table=True):
    """폐기·재생성을 전부 기록한다. 애매한 사유는 남기지 않는다."""

    __tablename__ = "generation_log"

    id: str = PrimaryKey()
    set_id: str = Field(foreign_key="carousel_set.id", index=True)
    slide_index: int | None = Field(default=None)
    stage: PipelineStage = Field(index=True)
    attempt: int = Field(default=1, ge=1)
    verdict: GenerationVerdict
    #: 판정 근거. quality_rules.yaml의 min_reason_chars를 만족해야 한다.
    reason: str
    cost: float | None = Field(default=None)
    duration_ms: int | None = Field(default=None)
    created_at: datetime = TimestampField()
