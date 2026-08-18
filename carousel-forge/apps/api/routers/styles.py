"""/styles — StyleDNA 추출·검증·활성화 (A1 StyleForensics, M3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from apps.api.deps import get_session
from apps.api.models import StyleDNA

from ._pending import not_yet

router = APIRouter(prefix="/styles", tags=["styles"])


@router.get("")
def list_styles(account_id: str | None = None, session: Session = Depends(get_session)) -> list[StyleDNA]:
    stmt = select(StyleDNA)
    if account_id:
        stmt = stmt.where(StyleDNA.account_id == account_id)
    return list(session.exec(stmt).all())


@router.post("/extract", status_code=202)
def extract_style() -> None:
    raise not_yet("M3", "스크린샷/URL → StyleDNA 추출")


@router.get("/{style_id}/preview")
def style_preview(style_id: str) -> None:
    raise not_yet("M3", "검증 렌더 3장 미리보기")


@router.post("/{style_id}/activate")
def activate_style(style_id: str) -> None:
    raise not_yet("M3", "StyleDNA 활성화(사용자 승인 후 is_active=True)")
