"""검증 렌더 — 추출한 DNA가 원본을 닮았는지 눈으로 확인한다.

A1의 필수 절차다. 더미 주제로 3장을 뽑아 원본 피드와 **나란히** 놓고, 사용자가
"닮았다"고 승인해야 `StyleDNA.is_active = True`가 된다. 스타일 추출은 숫자로
맞았다고 끝나는 일이 아니라 결국 보고 판단하는 일이기 때문이다.

비교 시트도 브라우저로 만든다. Pillow는 픽셀을 **읽는** 데만 쓰고 글자를 그리는
데는 쓰지 않는다 — 한글 조판을 정확히 하려면 어차피 브라우저가 필요하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import FONTS_DIR, platform_spec
from core.render.html_renderer import SlideRenderer, chromium_executable
from core.render.model import FONT_FILES, RenderBlock, RenderSet, RenderSlide, Theme

#: 고정된 더미 주제. 매번 같은 문장을 써야 추출 결과끼리 비교가 된다.
#: 스타일만 보이게 하려는 것이므로 내용은 일부러 밋밋하게 둔다.
DUMMY_SLIDES: list[tuple[str, list[tuple[str, str]]]] = [
    ("hook", [
        ("eyebrow", "STYLE CHECK"),
        ("headline", "이 스타일이\n원본과 닮았나요"),
        ("subhead", "검증용 더미 카피입니다"),
    ]),
    ("point", [
        ("badge", "01"),
        ("headline", "본문 슬라이드는\n이렇게 보입니다"),
        ("body", "헤드라인과 본문의 크기 차이, 줄 간격, 여백을 확인해 주세요."),
    ]),
    ("cta", [
        ("headline", "마지막 장은\n이렇게 끝납니다"),
        ("cta", "저장 →"),
    ]),
]

_SHEET = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><style>
{faces}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:{width}px; background:#0f0f10; color:#e8e6e3;
  font-family:"Pretendard", sans-serif; padding:48px;
}}
h1 {{ font-size:34px; font-weight:800; letter-spacing:-0.02em; margin-bottom:8px; }}
.sub {{ font-size:17px; color:#9a9895; margin-bottom:36px; line-height:1.6; }}
.row {{ margin-bottom:40px; }}
.label {{
  font-size:15px; font-weight:700; letter-spacing:0.08em;
  color:#c8a15a; margin-bottom:14px; text-transform:uppercase;
}}
.label span {{ color:#7d7b78; font-weight:400; letter-spacing:0; text-transform:none; }}
.strip {{ display:flex; gap:14px; }}
.strip img {{
  width:{thumb}px; border-radius:6px; display:block;
  border:1px solid #2a2a2c;
}}
.verdict {{
  margin-top:12px; padding:20px 24px; border:1px solid #2a2a2c;
  border-radius:8px; background:#151517; font-size:16px; line-height:1.75;
}}
.verdict b {{ color:#c8a15a; }}
</style></head><body>
<h1>스타일 검증 렌더</h1>
<div class="sub">
  위는 벤치마크 원본, 아래는 추출한 StyleDNA로 더미 주제를 렌더한 결과입니다.<br>
  팔레트 · 타이포 크기 관계 · 텍스트 위치 · 여백이 같은 결로 읽히는지 봐 주세요.
</div>
{rows}
<div class="verdict">
  닮았다고 판단되면 이 DNA를 <b>활성화</b>하세요 (<code>is_active = True</code>).<br>
  다르면 활성화하지 말고 샘플을 더 넣어 다시 추출하는 편이 낫습니다 —
  어긋난 DNA로 만든 결과물은 전부 어긋납니다.
</div>
</body></html>
"""


@dataclass
class PreviewResult:
    preview_paths: list[Path]
    comparison_path: Path
    render_set: RenderSet


def build_preview_set(
    dna: dict[str, Any], *, platform: str, language: str, set_id: str = "stylecheck"
) -> RenderSet:
    spec = platform_spec(platform)
    theme = Theme.from_dna(dna, spec, spec.canvas)
    slides = []
    for index, (role, blocks) in enumerate(DUMMY_SLIDES, start=1):
        slides.append(
            RenderSlide(
                index=index,
                role=role,
                background_fill=theme.palette_background,
                blocks=[
                    RenderBlock(id=f"s{index:02d}_{r}", role=r, text=text)
                    for r, text in blocks
                ],
            )
        )
    return RenderSet(
        set_id=set_id,
        account="stylecheck",
        platform=platform,
        language=language,
        theme=theme,
        slides=slides,
    )


def _font_faces() -> str:
    weights = {"Regular": 400, "Bold": 700, "ExtraBold": 800}
    return "\n".join(
        f'@font-face {{ font-family:"{family}"; '
        f'src:url("{(FONTS_DIR / filename).as_uri()}") format("woff2"); '
        f"font-weight:{weights[style]}; font-style:normal; font-display:block; }}"
        for (family, style), filename in FONT_FILES.items()
    )


def render_verification(
    dna: dict[str, Any],
    *,
    originals: list[Path],
    out_dir: Path,
    platform: str = "instagram",
    language: str = "ko",
) -> PreviewResult:
    """더미 3장을 렌더하고 원본과 나란히 놓은 비교 시트를 만든다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = out_dir / "preview"
    work_dir = out_dir / ".work"

    render_set = build_preview_set(dna, platform=platform, language=language)
    measurements = SlideRenderer().render_set(
        render_set, work_dir=work_dir, png_dir=preview_dir, image_format="png"
    )
    preview_paths = [m.png_path for m in measurements if m.png_path]

    thumb = 240
    shown_originals = originals[:9]
    rows = []
    for label, note, paths in (
        ("원본 피드", f"{len(originals)}장 중 {len(shown_originals)}장", shown_originals),
        ("추출 스타일로 렌더", "더미 주제 3장", preview_paths),
    ):
        strip = "".join(f'<img src="{p.resolve().as_uri()}">' for p in paths)
        rows.append(
            f'<div class="row"><div class="label">{label} <span>· {note}</span></div>'
            f'<div class="strip">{strip}</div></div>'
        )

    width = 48 * 2 + thumb * max(len(shown_originals), len(preview_paths)) + 14 * 8
    sheet_html = _SHEET.format(
        faces=_font_faces(), width=width, thumb=thumb, rows="\n".join(rows)
    )
    sheet_path = work_dir / "comparison.html"
    sheet_path.write_text(sheet_html, encoding="utf-8")

    comparison_path = out_dir / "comparison.png"
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_executable())
        page = browser.new_page(viewport={"width": width, "height": 1200})
        try:
            page.goto(sheet_path.as_uri(), wait_until="load")
            page.wait_for_function("document.fonts.status === 'loaded'")
            page.screenshot(path=str(comparison_path), full_page=True)
        finally:
            browser.close()

    return PreviewResult(
        preview_paths=preview_paths,
        comparison_path=comparison_path,
        render_set=render_set,
    )
