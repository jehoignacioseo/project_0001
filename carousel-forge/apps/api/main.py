"""Carousel Forge API.

M0/M1 시점의 표면: 헬스체크, 플랫폼 규격 조회, 계정 CRUD, 그리고 이미 렌더된
세트의 내보내기 파일 서빙. 나머지 엔드포인트는 선언돼 있지만 501을 낸다.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from apps.api.deps import get_session
from apps.api.models import Account, Language, Platform
from apps.api.routers import carousels, exports, library, styles, topics
from core.config import platform_keys, platform_spec, platforms_are_stale, platforms_verified_at

app = FastAPI(
    title="Carousel Forge API",
    version="0.1.0",
    description="스타일 × 주제 → 업로드 가능한 캐러셀 + Figma 편집 가능 내보내기",
)

for router in (styles, topics, carousels, exports, library):
    app.include_router(router.router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, object]:
    stale = platforms_are_stale()
    return {
        "status": "ok",
        "platforms_verified_at": str(platforms_verified_at()),
        # 규격은 변한다. 오래된 규격으로 조용히 렌더하지 않도록 경고를 노출한다.
        "platforms_stale": stale,
        "warning": "platforms.yaml 규격 확인일이 180일을 넘었다. 재검증하라." if stale else None,
    }


@app.get("/platforms", tags=["meta"])
def list_platforms() -> dict[str, object]:
    out = {}
    for key in platform_keys():
        spec = platform_spec(key)
        out[key] = {
            "display_name": spec.display_name,
            "canvas": {"width": spec.canvas.width, "height": spec.canvas.height, "ratio": spec.canvas.ratio},
            "max_slides": spec.max_slides,
            "safe_margin_px": spec.safe_margin_px,
            "caption_max_chars": spec.caption_max_chars,
            "caption_fold_at": spec.caption_fold_at,
            "title_max_chars": spec.title_max_chars,
            "hashtag_max": spec.hashtag_max,
        }
    return out


class AccountCreate(BaseModel):
    handle: str
    display_name: str
    platform: Platform
    default_language: Language = Language.KO
    brand_voice_note: str | None = None


@app.post("/accounts", tags=["accounts"], status_code=201)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)) -> Account:
    existing = session.exec(select(Account).where(Account.handle == payload.handle)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"이미 있는 핸들: {payload.handle}")
    account = Account(**payload.model_dump())
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@app.get("/accounts", tags=["accounts"])
def list_accounts(session: Session = Depends(get_session)) -> list[Account]:
    return list(session.exec(select(Account)).all())
