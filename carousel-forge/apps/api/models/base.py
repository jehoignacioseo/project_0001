"""테이블 공통 뼈대."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


def PrimaryKey() -> Any:  # noqa: N802 — 필드 팩토리라 클래스처럼 읽히게 둔다
    """SQLite/PostgreSQL 어디서나 동일하게 동작하는 문자열 UUID PK."""
    return Field(default_factory=new_id, primary_key=True, max_length=32)


def JsonField(default_factory: Any = dict, nullable: bool = False) -> Any:  # noqa: N802
    """JSON 컬럼. 스키마 검증은 Pydantic 계약(apps/api/schemas)이 담당한다."""
    return Field(
        default_factory=default_factory,
        sa_column=Column(JSON, nullable=nullable),
    )


def TimestampField(*, on_update: bool = False) -> Any:  # noqa: N802
    return Field(
        default_factory=utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            default=utcnow,
            onupdate=utcnow if on_update else None,
        ),
    )
