"""/library — 계정별 축적·열람·리믹스·성과 입력. M8."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from apps.api.deps import get_session
from apps.api.models import CarouselSet

from ._pending import not_yet

router = APIRouter(prefix="/library", tags=["library"])


@router.get("")
def browse(
    account_id: str | None = None,
    platform: str | None = None,
    lang: str | None = None,
    session: Session = Depends(get_session),
) -> list[CarouselSet]:
    """모든 세트는 축적되며 삭제되지 않는다 — archived 상태만 존재한다."""
    stmt = select(CarouselSet)
    if account_id:
        stmt = stmt.where(CarouselSet.account_id == account_id)
    if platform:
        stmt = stmt.where(CarouselSet.platform == platform)
    if lang:
        stmt = stmt.where(CarouselSet.language == lang)
    return list(session.exec(stmt).all())


@router.post("/{set_id}/remix")
def remix(set_id: str) -> None:
    raise not_yet("M8", "리믹스(주제/언어/스타일만 교체)")


@router.post("/{set_id}/metrics")
def record_metrics(set_id: str) -> None:
    raise not_yet("M8", "성과 피드백 입력")
