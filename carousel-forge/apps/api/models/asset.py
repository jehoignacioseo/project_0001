"""Asset — 생성/렌더된 모든 파일. 폐기본도 사유와 함께 남긴다 (절대 규칙 #9)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from .base import PrimaryKey, TimestampField
from .enums import AssetKind


class Asset(SQLModel, table=True):
    __tablename__ = "asset"

    id: str = PrimaryKey()
    set_id: str | None = Field(default=None, foreign_key="carousel_set.id", index=True)
    kind: AssetKind = Field(index=True)

    path: str
    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    mime: str = Field(default="image/png", max_length=80)
    provider: str | None = Field(default=None, max_length=80)

    generation_prompt: str | None = Field(default=None)
    seed: int | None = Field(default=None)

    #: 폐기해도 파일과 레코드는 지우지 않는다. 품질 패턴 학습 자산이다.
    is_discarded: bool = Field(default=False, index=True)
    discard_reason: str | None = Field(default=None)

    created_at: datetime = TimestampField()
