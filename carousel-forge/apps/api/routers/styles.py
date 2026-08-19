"""/styles — StyleDNA 추출·검증 렌더·활성화 (A1 StyleForensics).

승인 절차가 이 라우터의 핵심이다. 추출된 DNA는 **바로 쓰이지 않는다.**
검증 렌더를 사람이 보고 "닮았다"고 승인해야 `is_active=True`가 된다. 어긋난
DNA로 만든 결과물은 전부 어긋나므로, 이 관문을 자동으로 통과시키지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from apps.api.deps import get_session
from apps.api.models import Account, Language, Platform, StyleDNA, StyleSourceType
from core.agents import StyleForensics
from core.agents.base import AgentContext
from core.agents.forensics import render_verification
from core.agents.style_forensics import MIN_SAMPLES, ForensicsError
from core.config import STORAGE_DIR

router = APIRouter(prefix="/styles", tags=["styles"])


def _preview_dir(style_id: str) -> Path:
    return STORAGE_DIR / "styles" / style_id


class ExtractRequest(BaseModel):
    account_id: str
    name: str
    screenshots: list[str] = Field(
        min_length=1, description="벤치마크 피드 스크린샷 경로. 최소 6장을 권한다."
    )
    captions: list[str] = Field(
        default_factory=list,
        description="같은 게시물들의 본문 캡션. 없으면 말투·이모지·해시태그는 추정값이 된다.",
    )
    platform: Platform = Platform.INSTAGRAM
    language: Language = Language.KO
    source_type: StyleSourceType = StyleSourceType.SCREENSHOTS


class ExtractResponse(BaseModel):
    style_dna_id: str
    confidence_score: float
    warnings: list[str]
    report: str
    is_active: bool
    next_step: str


@router.get("")
def list_styles(
    account_id: str | None = None, session: Session = Depends(get_session)
) -> list[StyleDNA]:
    stmt = select(StyleDNA)
    if account_id:
        stmt = stmt.where(StyleDNA.account_id == account_id)
    return list(session.exec(stmt).all())


@router.post("/extract", status_code=201)
def extract_style(
    payload: ExtractRequest, session: Session = Depends(get_session)
) -> ExtractResponse:
    """스크린샷 → StyleDNA.

    동기 실행이다. 스펙은 비동기 job을 요구하지만 작업 큐(Celery/Redis)는 아직
    붙지 않았다 — 없는 큐를 흉내 내느니 오래 걸리는 요청으로 두는 편이 정직하다.
    """
    if session.get(Account, payload.account_id) is None:
        raise HTTPException(status_code=404, detail=f"계정을 찾을 수 없다: {payload.account_id}")

    paths = [Path(p) for p in payload.screenshots]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise HTTPException(status_code=400, detail=f"파일을 찾을 수 없다: {missing}")

    ctx = AgentContext(
        account_id=payload.account_id, platform=payload.platform, language=payload.language
    )
    try:
        result = StyleForensics().extract(paths, captions=payload.captions, ctx=ctx)
    except ForensicsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    version = (
        len(
            session.exec(
                select(StyleDNA).where(StyleDNA.account_id == payload.account_id)
            ).all()
        )
        + 1
    )
    record = StyleDNA(
        account_id=payload.account_id,
        name=payload.name,
        version=version,
        source_type=payload.source_type,
        source_refs=[str(p) for p in paths],
        dna=result.dna,
        confidence_score=result.confidence_score,
        is_active=False,        # 승인 전에는 절대 활성화하지 않는다
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    return ExtractResponse(
        style_dna_id=record.id,
        confidence_score=result.confidence_score,
        warnings=result.warnings,
        report=result.report(),
        is_active=False,
        next_step=(
            f"GET /styles/{record.id}/preview 로 검증 렌더를 만들고, 원본과 나란히 본 뒤 "
            f"POST /styles/{record.id}/activate 로 승인하라."
        ),
    )


class PreviewResponse(BaseModel):
    style_dna_id: str
    comparison_url: str
    preview_count: int
    note: str


@router.post("/{style_id}/preview")
def build_preview(style_id: str, session: Session = Depends(get_session)) -> PreviewResponse:
    """검증 렌더 — 더미 주제 3장 + 원본과의 비교 시트를 만든다."""
    record = session.get(StyleDNA, style_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"StyleDNA를 찾을 수 없다: {style_id}")

    originals = [Path(p) for p in record.source_refs if Path(p).exists()]
    result = render_verification(
        record.dna,
        originals=originals,
        out_dir=_preview_dir(style_id),
        platform=(session.get(Account, record.account_id).platform if record.account_id else "instagram"),
    )
    return PreviewResponse(
        style_dna_id=style_id,
        comparison_url=f"/styles/{style_id}/preview.png",
        preview_count=len(result.preview_paths),
        note="원본과 나란히 보고 닮았다고 판단되면 activate 하라.",
    )


@router.get("/{style_id}/preview.png")
def get_preview_image(style_id: str) -> FileResponse:
    path = _preview_dir(style_id) / "comparison.png"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"검증 렌더가 아직 없다. 먼저 POST /styles/{style_id}/preview 를 호출하라.",
        )
    return FileResponse(path, media_type="image/png")


class ActivateRequest(BaseModel):
    approved: bool = Field(description="검증 렌더가 원본과 닮았는가")
    reviewer_note: str | None = None


class ActivateResponse(BaseModel):
    style_dna_id: str
    is_active: bool
    deactivated: list[str] = Field(default_factory=list)
    message: str


@router.post("/{style_id}/activate")
def activate_style(
    style_id: str, payload: ActivateRequest, session: Session = Depends(get_session)
) -> ActivateResponse:
    """사람이 승인해야만 활성화된다."""
    record = session.get(StyleDNA, style_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"StyleDNA를 찾을 수 없다: {style_id}")

    if not payload.approved:
        record.is_active = False
        session.add(record)
        session.commit()
        return ActivateResponse(
            style_dna_id=style_id,
            is_active=False,
            message="승인되지 않았다. 샘플을 더 넣어 다시 추출하는 편이 낫다.",
        )

    if not _preview_dir(style_id).joinpath("comparison.png").exists():
        raise HTTPException(
            status_code=409,
            detail=(
                "검증 렌더 없이 활성화할 수 없다. 원본과 나란히 보지 않고 승인하면 "
                f"이 관문이 의미가 없다. 먼저 POST /styles/{style_id}/preview 를 호출하라."
            ),
        )

    # 계정당 활성 DNA는 하나다. 이전 것은 내린다(삭제하지 않는다 — 버전은 남는다).
    others = session.exec(
        select(StyleDNA).where(
            StyleDNA.account_id == record.account_id, StyleDNA.is_active == True  # noqa: E712
        )
    ).all()
    deactivated = []
    for other in others:
        if other.id != style_id:
            other.is_active = False
            session.add(other)
            deactivated.append(other.id)

    record.is_active = True
    session.add(record)

    account = session.get(Account, record.account_id)
    if account is not None:
        account.active_style_dna_id = record.id
        session.add(account)

    session.commit()

    message = f"활성화됐다 (v{record.version})."
    if record.confidence_score < 0.6:
        message += (
            f" 다만 신뢰도가 {record.confidence_score:.2f}로 낮다 — "
            f"샘플 {MIN_SAMPLES}장 이상에서 다시 뽑는 편을 권한다."
        )
    return ActivateResponse(
        style_dna_id=style_id, is_active=True, deactivated=deactivated, message=message
    )
