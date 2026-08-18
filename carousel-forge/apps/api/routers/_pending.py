"""아직 구현되지 않은 엔드포인트를 정직하게 501로 막는다."""

from __future__ import annotations

from fastapi import HTTPException, status


def not_yet(milestone: str, what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{what} — {milestone}에서 구현 예정. 현재 마일스톤(M0/M1) 범위 밖.",
    )
