"""렌더 파이프라인 — 텍스트를 이미지에 굽지 않는 유일한 경로.

    RenderSet ──┬─→ PNG/JPG  (01_upload)
                ├─→ SVG      (02_figma)   <text>/<tspan>, 편집 가능
                ├─→ manifest (02_figma)   실측 좌표
                └─→ TXT/JSON (03_copy)
"""

from .geometry import Overflow, contrast_ratio, find_overflows
from .html_renderer import RenderError, SlideMeasurement, SlideRenderer, render_html
from .manifest import build_manifest, validate_manifest, write_manifest
from .model import RenderBlock, RenderSet, RenderSlide, Theme, TypeStyle
from .pipeline import RenderReport, render_and_export
from .svg_exporter import assert_svg_rules, build_svg

__all__ = [
    "Overflow",
    "RenderBlock",
    "RenderError",
    "RenderReport",
    "RenderSet",
    "RenderSlide",
    "SlideMeasurement",
    "SlideRenderer",
    "Theme",
    "TypeStyle",
    "assert_svg_rules",
    "build_manifest",
    "build_svg",
    "contrast_ratio",
    "find_overflows",
    "render_and_export",
    "render_html",
    "validate_manifest",
    "write_manifest",
]
