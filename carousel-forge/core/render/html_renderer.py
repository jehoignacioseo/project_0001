"""Jinja2 HTML → Playwright(Chromium) → PNG + 실측 기하.

Pillow로 이미지 위에 글자를 그리는 방식은 쓰지 않는다. 한글/중문 조판과 웹폰트를
정밀하게 제어하려면 브라우저의 조판 엔진이 필요하고, 무엇보다 **같은 HTML에서
PNG와 SVG가 함께 나와야** 좌표 오차가 0이 되기 때문이다.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from playwright.sync_api import sync_playwright

from core.config import FONTS_DIR, TEMPLATES_DIR
from core.render.model import FONT_FILES, RenderSet, RenderSlide

#: 폰트 파일명 → CSS font-weight
_STYLE_WEIGHT = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800}


class RenderError(RuntimeError):
    pass


def chromium_executable() -> str | None:
    """설치된 Chromium 경로. 없으면 None(= Playwright 번들 사용).

    이 환경은 Playwright 브라우저를 미리 깔아두고 `PLAYWRIGHT_BROWSERS_PATH`로
    가리킨다. 파이썬 Playwright 버전이 기대하는 리비전과 다를 수 있으므로,
    있으면 실행 파일을 직접 지정한다.
    """
    explicit = os.environ.get("CAROUSEL_FORGE_CHROMIUM")
    if explicit:
        if not Path(explicit).exists():
            raise RenderError(f"CAROUSEL_FORGE_CHROMIUM 경로에 파일이 없다: {explicit}")
        return explicit

    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if root:
        candidate = Path(root) / "chromium"
        if candidate.exists():
            return str(candidate)
        for found in sorted(Path(root).glob("chromium-*/chrome-linux/chrome")):
            return str(found)

    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


@dataclass
class SlideMeasurement:
    """한 슬라이드의 실측 결과. manifest와 SVG가 모두 이 값에서 파생된다."""

    index: int
    role: str
    layout_template: str
    canvas: dict[str, float]
    safe_area: dict[str, float]
    background: dict[str, Any] | None
    blocks: list[dict[str, Any]]
    png_path: Path | None = None
    html_path: Path | None = None
    source: RenderSlide | None = field(default=None, repr=False)


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
        undefined=StrictUndefined,     # 템플릿 변수 오타를 조용히 빈 문자열로 넘기지 않는다
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _font_faces(render_set: RenderSet) -> list[dict[str, Any]]:
    faces = []
    for (family, style), filename in FONT_FILES.items():
        path = FONTS_DIR / filename
        if not path.exists():
            raise RenderError(
                f"폰트 파일이 없다: {path}. `python scripts/fetch_fonts.py`로 내려받아라."
            )
        faces.append({"family": family, "url": path.as_uri(), "weight": _STYLE_WEIGHT[style]})
    return faces


def _template_context(render_set: RenderSet, slide: RenderSlide, background_href: str | None) -> dict[str, Any]:
    theme = render_set.theme
    blocks_view = []
    by_role: dict[str, Any] = {}
    bullets: list[Any] = []

    for block in slide.blocks:
        style = theme.style_for(block.role)
        view = {
            "id": block.id,
            "role": block.role,
            "style": style,
            "color": block.color or theme.palette_text,
            "emphasis_color": block.emphasis_color or theme.palette_accent,
            "align": theme.alignment if theme.alignment != "justified" else "justify",
            "segments": [{"text": t, "emphasis": em} for t, em in block.segments()],
        }
        blocks_view.append(view)
        if block.role == "bullet":
            bullets.append(view)
        else:
            by_role[block.role] = view

    overlay_color = theme.palette_background if theme.overlay_type != "none" else "transparent"
    return {
        "set_id": render_set.set_id,
        "language": render_set.language,
        "canvas": render_set.canvas,
        "theme": theme,
        "slide": slide,
        "blocks": blocks_view,
        "by_role": by_role,
        "bullets": bullets,
        "fonts": _font_faces(render_set),
        "background_href": background_href,
        "overlay_color": overlay_color,
        "gradient_direction": "to top" if theme.text_zone == "bottom" else "to bottom",
    }


def render_html(render_set: RenderSet, slide: RenderSlide, background_href: str | None) -> str:
    env = _jinja_env()
    template = env.get_template(f"{slide.template()}.html.j2")
    return template.render(**_template_context(render_set, slide, background_href))


class SlideRenderer:
    """Playwright 브라우저 한 개를 열어 세트 전체를 렌더한다.

    한 번 띄운 페이지에서 PNG 스크린샷과 기하 측정을 **함께** 수행한다.
    두 결과가 같은 레이아웃에서 나와야 좌표가 어긋나지 않는다.
    """

    def __init__(self, *, device_scale_factor: int = 1) -> None:
        self.device_scale_factor = device_scale_factor
        self._measure_js = (Path(__file__).parent / "measure.js").read_text(encoding="utf-8")

    def render_set(
        self,
        render_set: RenderSet,
        *,
        work_dir: Path,
        png_dir: Path,
        background_dir: Path | None = None,
        image_format: str = "png",
        quality: int | None = None,
    ) -> list[SlideMeasurement]:
        render_set.validate()
        work_dir.mkdir(parents=True, exist_ok=True)
        png_dir.mkdir(parents=True, exist_ok=True)
        canvas = render_set.canvas
        results: list[SlideMeasurement] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=chromium_executable(),
                args=["--force-color-profile=srgb", "--font-render-hinting=none"],
            )
            page = browser.new_page(
                viewport={"width": canvas.width, "height": canvas.height},
                device_scale_factor=self.device_scale_factor,
            )
            try:
                for slide in render_set.slides:
                    results.append(
                        self._render_one(
                            page, render_set, slide,
                            work_dir=work_dir, png_dir=png_dir,
                            background_dir=background_dir,
                            image_format=image_format, quality=quality,
                        )
                    )
            finally:
                browser.close()
        return results

    def _render_one(
        self,
        page,
        render_set: RenderSet,
        slide: RenderSlide,
        *,
        work_dir: Path,
        png_dir: Path,
        background_dir: Path | None,
        image_format: str,
        quality: int | None,
    ) -> SlideMeasurement:
        # 배경은 HTML 파일 기준 상대 경로로 참조한다. 내보내기 ZIP 안에서도
        # 같은 상대 구조(02_figma/slide_XX.svg ↔ 02_figma/backgrounds/bg_XX.png)를
        # 유지하기 위해서다.
        background_href = None
        if slide.background:
            if background_dir is None:
                raise RenderError(f"슬라이드 {slide.index}에 배경이 있는데 background_dir이 없다")
            bg_path = (background_dir / slide.background).resolve()
            if not bg_path.exists():
                raise RenderError(f"배경 파일이 없다: {bg_path}")
            background_href = os.path.relpath(bg_path, work_dir).replace(os.sep, "/")

        html = render_html(render_set, slide, background_href)
        html_path = work_dir / f"slide_{slide.index:02d}.html"
        html_path.write_text(html, encoding="utf-8")

        page.goto(html_path.as_uri(), wait_until="load")
        # 폰트가 다 붙기 전에 찍으면 폴백 폰트로 렌더된 PNG가 나온다.
        page.evaluate("document.fonts.ready")
        page.wait_for_function("document.fonts.status === 'loaded'")

        ext = "jpg" if image_format in ("jpg", "jpeg") else image_format
        png_path = png_dir / f"slide_{slide.index:02d}.{ext}"
        page.screenshot(
            path=str(png_path),
            type="jpeg" if ext == "jpg" else "png",
            quality=quality if ext == "jpg" else None,
        )

        measured = page.evaluate(self._measure_js)
        return SlideMeasurement(
            index=slide.index,
            role=slide.role,
            layout_template=slide.template(),
            canvas=measured["canvas"],
            safe_area=measured["safe_area"],
            background=measured["background"],
            blocks=measured["blocks"],
            png_path=png_path,
            html_path=html_path,
            source=slide,
        )
