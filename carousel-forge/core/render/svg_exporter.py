"""실측 기하 → Figma에서 편집 가능한 SVG.

섹션 6.2 규칙을 그대로 지킨다:

  ✅ 텍스트는 <text>/<tspan>. 절대 <path>로 아웃라인화하지 않는다.
  ✅ 배경은 <image href="…"> 참조 (base64 임베드는 옵션)
  ✅ font-family는 실제 폰트명 + 폴백 체인
  ✅ 레이어 이름은 id 속성으로 (s01_headline, s01_body, s01_bg)
  ✅ 슬라이드마다 독립 SVG, viewBox는 캔버스 크기
  ✅ <g id="text-layer">로 묶어 Figma가 프레임으로 인식하게 한다
  ❌ CSS 클래스 대신 인라인 style/presentation 속성 (Figma의 CSS 파싱이 불완전)
  ❌ filter, mask 남용 금지 (Figma 임포트 시 래스터화됨)

텍스트를 이미지에 굽는 순간 이 프로그램은 실패한 것이므로, 여기에는
텍스트를 래스터화하는 경로가 아예 없다.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from xml.sax.saxutils import escape

from core.render.html_renderer import SlideMeasurement
from core.render.model import RenderSet

#: SVG 안에서 쓰면 Figma 임포트가 래스터화해 버리는 요소들.
FORBIDDEN_ELEMENTS = ("<filter", "<mask", "<clipPath", "<path")

_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)")


class SvgExportError(RuntimeError):
    pass


def css_color_to_hex(value: str) -> str:
    """`rgb(17, 17, 17)` → `#111111`. Figma가 읽는 형태로 고정한다."""
    value = value.strip()
    if value.startswith("#"):
        if len(value) == 4:
            return "#" + "".join(c * 2 for c in value[1:])
        return value.lower()
    m = _RGB_RE.match(value)
    if not m:
        raise SvgExportError(f"해석할 수 없는 색 값: {value!r}")
    r, g, b = (int(round(float(m.group(i)))) for i in (1, 2, 3))
    return f"#{r:02x}{g:02x}{b:02x}"


def _font_family_attr(css_family: str) -> str:
    """브라우저가 돌려준 font-family 문자열을 그대로 폴백 체인으로 쓴다."""
    names = [n.strip().strip('"\'') for n in css_family.split(",") if n.strip()]
    return ", ".join(f"'{n}'" if " " in n else n for n in names)


def _weight_to_style(weight: int) -> str:
    return {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}.get(
        weight, "Regular"
    )


def build_svg(
    render_set: RenderSet,
    measurement: SlideMeasurement,
    *,
    background_href: str | None = None,
    embed_background: bool = False,
    background_file: Path | None = None,
) -> str:
    width = int(round(measurement.canvas["width"]))
    height = int(round(measurement.canvas["height"]))
    idx = f"s{measurement.index:02d}"
    theme = render_set.theme

    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<title>{escape(render_set.set_id)} — slide {measurement.index:02d} '
        f'({escape(measurement.role)})</title>',
        # 배경 레이어 — 텍스트 없는 원본. 텍스트와 끝까지 분리된 채로 남는다.
        f'<g id="{idx}_background">',
        f'<rect id="{idx}_bg_fill" x="0" y="0" width="{width}" height="{height}" '
        f'fill="{css_color_to_hex(theme.palette_background)}"/>',
    ]

    if measurement.background is not None:
        href = background_href
        if embed_background:
            if background_file is None or not background_file.exists():
                raise SvgExportError("embed_background=True인데 배경 파일 경로가 없다")
            data = base64.b64encode(background_file.read_bytes()).decode("ascii")
            href = f"data:image/png;base64,{data}"
        if href is None:
            raise SvgExportError("배경이 있는데 background_href가 없다")
        # preserveAspectRatio="xMidYMid slice"가 CSS object-fit: cover와 같은 동작이다.
        parts.append(
            f'<image id="{idx}_bg" href="{escape(href, {chr(34): "&quot;"})}" '
            f'xlink:href="{escape(href, {chr(34): "&quot;"})}" '
            f'x="0" y="0" width="{width}" height="{height}" '
            f'preserveAspectRatio="xMidYMid slice"/>'
        )

    if theme.overlay_type == "scrim" and theme.overlay_opacity > 0:
        parts.append(
            f'<rect id="{idx}_overlay" x="0" y="0" width="{width}" height="{height}" '
            f'fill="{css_color_to_hex(theme.palette_background)}" '
            f'fill-opacity="{theme.overlay_opacity}"/>'
        )
    elif theme.overlay_type == "gradient" and theme.overlay_opacity > 0:
        stop = css_color_to_hex(theme.palette_background)
        y1, y2 = ("1", "0") if theme.text_zone == "bottom" else ("0", "1")
        parts.append(
            f'<defs><linearGradient id="{idx}_overlay_grad" x1="0" y1="{y1}" x2="0" y2="{y2}">'
            f'<stop offset="0" stop-color="{stop}" stop-opacity="{theme.overlay_opacity}"/>'
            f'<stop offset="1" stop-color="{stop}" stop-opacity="0"/>'
            f"</linearGradient></defs>"
        )
        parts.append(
            f'<rect id="{idx}_overlay" x="0" y="0" width="{width}" height="{height}" '
            f'fill="url(#{idx}_overlay_grad)"/>'
        )

    parts.append("</g>")

    # 텍스트 레이어 — Figma가 프레임으로 인식하도록 하나로 묶는다.
    parts.append('<g id="text-layer">')
    for block in measurement.blocks:
        parts.append(_block_to_text(block))
    parts.append("</g>")
    parts.append("</svg>")

    svg = "\n".join(parts)
    assert_svg_rules(svg)
    return svg


def _block_to_text(block: dict) -> str:
    runs = block["runs"]
    if not runs:
        return f'<g id="{escape(block["id"])}"/>'

    first = runs[0]
    family = _font_family_attr(first["font_family"])
    letter_spacing = first["letter_spacing"]

    # <text>에는 블록 공통 스타일을, <tspan>에는 실측 좌표와 run별 차이를 싣는다.
    attrs = [
        f'id="{escape(block["id"])}"',
        f'font-family="{escape(family, {chr(34): "&quot;"})}"',
        f'font-weight="{first["font_weight"]}"',
        f'font-size="{first["font_size"]:g}"',
        f'fill="{css_color_to_hex(first["color"])}"',
        'text-anchor="start"',   # 좌표는 실측값이므로 정렬은 x로 이미 표현돼 있다
        'xml:space="preserve"',
        f'data-role="{escape(block["role"])}"',
        f'data-figma-style="{_weight_to_style(first["font_weight"])}"',
    ]
    if letter_spacing:
        attrs.append(f'letter-spacing="{letter_spacing:g}"')

    spans = []
    for run in runs:
        span_attrs = [f'x="{run["x"]:.2f}"', f'y="{run["baseline"]:.2f}"']
        if run["font_weight"] != first["font_weight"]:
            span_attrs.append(f'font-weight="{run["font_weight"]}"')
        if run["font_size"] != first["font_size"]:
            span_attrs.append(f'font-size="{run["font_size"]:g}"')
        if css_color_to_hex(run["color"]) != css_color_to_hex(first["color"]):
            span_attrs.append(f'fill="{css_color_to_hex(run["color"])}"')
        spans.append(f'<tspan {" ".join(span_attrs)}>{escape(run["text"])}</tspan>')

    return f'<text {" ".join(attrs)}>' + "".join(spans) + "</text>"


def assert_svg_rules(svg: str) -> None:
    """섹션 6.2 금지 규칙을 어긴 SVG는 내보내지 않는다."""
    problems = [f"금지된 요소 {el!r}가 들어 있다" for el in FORBIDDEN_ELEMENTS if el in svg]
    if "<text" not in svg:
        problems.append("<text> 요소가 하나도 없다 — 텍스트가 편집 불가능하게 나갔을 수 있다")
    if 'class="' in svg:
        problems.append("CSS 클래스를 쓰고 있다 — Figma의 CSS 파싱이 불완전하므로 인라인 속성만 쓴다")
    if problems:
        raise SvgExportError("SVG 내보내기 규칙 위반:\n  - " + "\n  - ".join(problems))
