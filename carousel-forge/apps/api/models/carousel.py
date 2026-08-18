"""CarouselSet / Slide — 캐러셀 1세트 = 게시물 1개, 그리고 그 낱장."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Field, SQLModel, UniqueConstraint

from .base import JsonField, PrimaryKey, TimestampField
from .enums import Language, Platform, SetStatus, SlideRole, VariantType


class CarouselSet(SQLModel, table=True):
    __tablename__ = "carousel_set"

    id: str = PrimaryKey()
    account_id: str = Field(foreign_key="account.id", index=True)
    style_dna_id: str | None = Field(default=None, foreign_key="style_dna.id", index=True)
    topic_brief_id: str | None = Field(default=None, foreign_key="topic_brief.id", index=True)

    platform: Platform = Field(index=True)
    language: Language = Field(index=True)
    slide_count: int = Field(default=0, ge=0)
    status: SetStatus = Field(default=SetStatus.DRAFT, index=True)

    #: schemas/copy.schema.json 의 Caption
    caption: dict[str, Any] = JsonField()
    hashtags: list[str] = JsonField(default_factory=list)

    #: A9 QualityGate 판정 결과 전문 (통과/폐기 사유 포함)
    quality_report: dict[str, Any] = JsonField()
    #: A6 FactChecker 결과 — 업로드 전 사용자가 확인한다
    fact_report: dict[str, Any] = JsonField()

    #: 번역/변주 시 원본 참조
    parent_set_id: str | None = Field(default=None, foreign_key="carousel_set.id", index=True)
    variant_type: VariantType = Field(default=VariantType.ORIGINAL)

    created_at: datetime = TimestampField()
    updated_at: datetime = TimestampField(on_update=True)


class Slide(SQLModel, table=True):
    """캐러셀 낱장.

    `copy_blocks`는 텍스트 레이어의 단일 진실 소스다. `render_asset_id`가 가리키는
    합성본은 여기서 파생된 결과물일 뿐이며, 텍스트를 이미지에 굽는 일은 없다
    (절대 규칙 #1).
    """

    __tablename__ = "slide"
    __table_args__ = (UniqueConstraint("set_id", "index", name="uq_slide_set_index"),)

    id: str = PrimaryKey()
    set_id: str = Field(foreign_key="carousel_set.id", index=True)
    index: int = Field(ge=1)
    role: SlideRole

    #: core/render/templates 안의 템플릿 ID (예: "point")
    layout_template: str = Field(max_length=80)

    background_asset_id: str | None = Field(default=None, foreign_key="asset.id")
    #: schemas/copy.schema.json 의 CopyBlock 목록
    copy_blocks: list[dict[str, Any]] = JsonField(default_factory=list)

    render_asset_id: str | None = Field(default=None, foreign_key="asset.id")
    svg_path: str | None = Field(default=None)
    notes: str | None = Field(default=None)
