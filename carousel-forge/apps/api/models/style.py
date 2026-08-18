"""StyleDNA — 벤치마크 계정에서 추출한 스타일 자산 (버전 관리됨)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel

from .base import JsonField, PrimaryKey, TimestampField
from .enums import StyleSourceType


class StyleDNA(SQLModel, table=True):
    __tablename__ = "style_dna"

    id: str = PrimaryKey()
    account_id: str = Field(foreign_key="account.id", index=True)
    name: str = Field(max_length=200)
    version: int = Field(default=1)
    source_type: StyleSourceType

    #: 스크린샷 경로 / 게시물 URL 등 추출 근거의 원본 참조
    source_refs: list[Any] = JsonField(default_factory=list)

    #: schemas/style_dna.schema.json 계약을 따르는 본체
    dna: dict[str, Any] = JsonField()

    #: 샘플 6개 미만이면 0.6 미만으로 표기하고 사용자에게 경고한다
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

    #: 검증 렌더를 사용자가 "닮았다"고 승인해야 True가 된다
    is_active: bool = Field(default=False, index=True)

    extracted_at: datetime = TimestampField()
