"""/exports — ZIP / manifest / SVG 내보내기.

manifest와 SVG는 M1 렌더 파이프라인의 산출물이다. 여기서는 이미 렌더된
세트의 파일을 돌려주며, 세트를 만들어 내는 파이프라인 자체는 M2 이후다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from core.config import STORAGE_DIR

from ._pending import not_yet

router = APIRouter(prefix="/exports", tags=["exports"])


def _set_dir(set_id: str):
    path = (STORAGE_DIR / "exports" / set_id).resolve()
    if not path.is_relative_to((STORAGE_DIR / "exports").resolve()):
        raise HTTPException(status_code=400, detail="잘못된 set_id")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"내보내기 결과가 없다: {set_id}")
    return path


@router.get("/{set_id}/manifest")
def get_manifest(set_id: str) -> FileResponse:
    """Figma 플러그인이 호출하는 계약 파일."""
    path = _set_dir(set_id) / "02_figma" / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="manifest.json이 아직 생성되지 않았다")
    return FileResponse(path, media_type="application/json")


@router.get("/{set_id}/svg/{index}")
def get_svg(set_id: str, index: int) -> FileResponse:
    path = _set_dir(set_id) / "02_figma" / f"slide_{index:02d}.svg"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"슬라이드 {index} SVG가 없다")
    return FileResponse(path, media_type="image/svg+xml")


@router.get("/{set_id}/zip")
def get_zip(set_id: str) -> None:
    raise not_yet("M4", "내보내기 ZIP 패키징")
