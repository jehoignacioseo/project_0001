"""/topics — 주제 정규화(A2)와 선제안(A3). M2·M5."""

from __future__ import annotations

from fastapi import APIRouter

from ._pending import not_yet

router = APIRouter(prefix="/topics", tags=["topics"])


@router.post("/ingest")
def ingest_topic() -> None:
    raise not_yet("M2", "문서/채팅/키워드/URL 통합 인테이크")


@router.get("/proposals")
def topic_proposals(account_id: str) -> None:
    raise not_yet("M5", "TrendScout 선제안 5개")
