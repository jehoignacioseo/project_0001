"""아직 구현되지 않은 엔드포인트를 정직하게 501로 막는다."""

from __future__ import annotations

from fastapi import HTTPException, status


def not_yet(milestone: str, what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{what} — {milestone}에서 구현 예정. 아직 이 엔드포인트로는 열려 있지 않다.",
    )
