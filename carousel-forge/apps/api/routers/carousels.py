"""/carousels — 세트 생성·조회·재생성·현지화. M2 이후."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from apps.api.deps import get_session
from apps.api.models import CarouselSet

from ._pending import not_yet

router = APIRouter(prefix="/carousels", tags=["carousels"])


@router.post("", status_code=202)
def create_carousel() -> None:
    raise not_yet("M2", "캐러셀 생성 파이프라인 기동")


@router.get("/{set_id}")
def get_carousel(set_id: str, session: Session = Depends(get_session)) -> CarouselSet:
    obj = session.get(CarouselSet, set_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"세트를 찾을 수 없다: {set_id}")
    return obj


@router.post("/{set_id}/regenerate")
def regenerate(set_id: str) -> None:
    raise not_yet("M4", "부분 재생성(세트/슬라이드 단위)")


@router.post("/{set_id}/localize")
def localize(set_id: str) -> None:
    # A10 Localizer 자체는 M7에서 동작한다(`scripts/demo_m7.py`). 여기서 막히는 것은
    # 에이전트가 아니라 **세트 영속화**다 — 이 엔드포인트는 저장된 세트를 읽어
    # 변주를 다시 저장해야 하는데, 세트를 쓰는 경로가 아직 API에 없다.
    raise not_yet("M8", "저장된 세트의 다국어·플랫폼 변주 (A10 자체는 scripts/demo_m7.py로 동작한다)")


@router.post("/{set_id}/approve")
def approve(set_id: str) -> None:
    raise not_yet("M4", "세트 승인")
