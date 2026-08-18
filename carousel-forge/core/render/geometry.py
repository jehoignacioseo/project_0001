"""기하 검사 — 안전영역 침범과 대비비.

여기 있는 값은 전부 실측 좌표에서 나온다. 판정 결과는 A9 QualityGate가
`text_overflow` / `contrast_below_wcag` 판정에 그대로 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import quality_rules
from core.render.html_renderer import SlideMeasurement
from core.render.svg_exporter import css_color_to_hex


@dataclass(frozen=True)
class Overflow:
    slide_index: int
    block_id: str
    side: str
    amount_px: float

    def __str__(self) -> str:
        return (
            f"슬라이드 {self.slide_index} {self.block_id}: 안전영역 {self.side} 방향으로 "
            f"{self.amount_px:.1f}px 침범"
        )


def find_overflows(measurement: SlideMeasurement) -> list[Overflow]:
    """텍스트가 안전영역을 벗어났는지 실측 좌표로 확인한다."""
    tolerance = float(quality_rules()["thresholds"]["safe_area_tolerance_px"])
    safe = measurement.safe_area
    left, top = safe["x"], safe["y"]
    right, bottom = left + safe["width"], top + safe["height"]

    out: list[Overflow] = []
    for block in measurement.blocks:
        for line in block["runs"]:
            checks = (
                ("left", left - line["x"]),
                ("top", top - line["y"]),
                ("right", (line["x"] + line["width"]) - right),
                ("bottom", (line["y"] + line["height"]) - bottom),
            )
            for side, amount in checks:
                if amount > tolerance:
                    out.append(Overflow(measurement.index, block["id"], side, amount))
    return out


def _relative_luminance(hex_color: str) -> float:
    value = css_color_to_hex(hex_color).lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(value[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 상대 명도 대비비."""
    lf, lb = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(lf, lb), min(lf, lb)
    return (lighter + 0.05) / (darker + 0.05)


def blend(foreground: str, background: str, alpha: float) -> str:
    """foreground를 alpha로 background 위에 올렸을 때의 합성 색 (스크림 계산용)."""
    fg = css_color_to_hex(foreground).lstrip("#")
    bg = css_color_to_hex(background).lstrip("#")
    out = []
    for i in (0, 2, 4):
        f, b = int(fg[i : i + 2], 16), int(bg[i : i + 2], 16)
        out.append(round(f * alpha + b * (1 - alpha)))
    return "#" + "".join(f"{c:02x}" for c in out)
