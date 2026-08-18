"""Account — 운영 계정. 스타일·산출물의 소유 단위."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, SQLModel

from .base import PrimaryKey, TimestampField
from .enums import Language, Platform


class Account(SQLModel, table=True):
    __tablename__ = "account"

    id: str = PrimaryKey()
    handle: str = Field(index=True, unique=True, max_length=120)
    display_name: str = Field(max_length=200)
    platform: Platform = Field(index=True)
    default_language: Language = Field(default=Language.KO)
    brand_voice_note: str | None = Field(default=None)

    #: account ↔ style_dna 는 서로를 참조한다(계정이 활성 DNA를 가리키고, DNA는
    #: 소속 계정을 가리킨다). 순환 FK라 테이블 생성 순서를 정할 수 없으므로
    #: use_alter로 제약을 나중에 붙인다.
    active_style_dna_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("style_dna.id", use_alter=True, name="fk_account_active_style_dna"),
            nullable=True,
        ),
    )
    created_at: datetime = TimestampField()
