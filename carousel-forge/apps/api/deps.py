"""FastAPI 의존성 — DB 세션, 설정 접근."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from core.config import STORAGE_DIR, database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///"):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
