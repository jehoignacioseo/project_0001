"""기하 검사 — 안전영역 침범과 대비비.

여기 있는 값은 전부 실측 좌표에서 나온다. 판정 결과는 A9 QualityGate가
`text_overflow` / `contrast_below_wcag` 판정에 그대로 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


# ── 실제 픽셀 기반 대비 판정 ────────────────────────────────────────────
#
# 팔레트 값끼리 대비를 재면 배경이 사진일 때 의미가 없다. 텍스트 뒤에 실제로
# 깔린 픽셀을 봐야 한다. `SlideMeasurement.background_png_path`는 텍스트를 숨기고
# 찍은 같은 레이아웃의 배경이므로 좌표가 그대로 맞는다.

@dataclass(frozen=True)
class ContrastFinding:
    slide_index: int
    block_id: str
    ratio: float
    required: float
    text_color: str
    worst_background: str

    @property
    def ok(self) -> bool:
        return self.ratio >= self.required

    def __str__(self) -> str:
        verdict = "충족" if self.ok else "미달"
        return (
            f"슬라이드 {self.slide_index} {self.block_id}: 대비 {self.ratio:.2f}:1 "
            f"({verdict}, 기준 {self.required}:1) — 글자 {self.text_color} / "
            f"가장 불리한 배경 {self.worst_background}"
        )


def _load_rgb(path: Path):
    from PIL import Image

    with Image.open(path) as img:
        return img.convert("RGB")


def worst_contrast_in_box(
    background_png: Path, box: dict[str, float], text_hex: str
) -> tuple[float, str]:
    """상자 안에서 **가장 대비가 나쁜** 배경 픽셀을 찾아 그 대비비를 돌려준다.

    평균을 쓰면 안 된다. 밝은 배경에 밝은 글자가 한쪽 귀퉁이에서만 겹쳐도 그
    부분은 읽히지 않는데, 평균은 그걸 가려 버린다.
    """
    image = _load_rgb(background_png)
    left = max(0, int(box["x"]))
    top = max(0, int(box["y"]))
    right = min(image.width, int(box["x"] + box["width"]) + 1)
    bottom = min(image.height, int(box["y"] + box["height"]) + 1)
    if right <= left or bottom <= top:
        return float("inf"), "#000000"

    region = image.crop((left, top, right, bottom))
    # 픽셀이 많으면 축소해서 본다. 최악값 탐색이라 축소는 평균화 효과가 있어
    # 아주 작은 점 하나는 놓칠 수 있지만, 글자가 얹히는 면적 기준으로는 충분하다.
    if region.width * region.height > 40_000:
        scale = (40_000 / (region.width * region.height)) ** 0.5
        region = region.resize((max(1, int(region.width * scale)), max(1, int(region.height * scale))))

    worst_ratio = float("inf")
    worst_hex = "#000000"
    for rgb in region.getdata():
        candidate = "#{:02x}{:02x}{:02x}".format(*rgb)
        ratio = contrast_ratio(text_hex, candidate)
        if ratio < worst_ratio:
            worst_ratio, worst_hex = ratio, candidate
    return worst_ratio, worst_hex


def check_contrast(measurement) -> list[ContrastFinding]:
    """슬라이드의 모든 카피 블록에 대해 WCAG 대비를 판정한다."""
    thresholds = quality_rules()["thresholds"]
    normal = float(thresholds["contrast_min_ratio"])
    large = float(thresholds["contrast_min_ratio_large"])

    if measurement.background_png_path is None:
        raise ValueError(
            "배경 전용 이미지가 없다. SlideRenderer(capture_background=True)로 렌더해야 "
            "대비를 실제 픽셀로 잴 수 있다."
        )

    findings: list[ContrastFinding] = []
    for block in measurement.blocks:
        text_hex = css_color_to_hex(block["color"])
        # WCAG는 굵고 큰 글자에 완화된 기준을 준다 (24px 이상, 또는 볼드 18.66px 이상).
        is_large = block["font_size"] >= 24 and block["font_weight"] >= 700 or block["font_size"] >= 32
        required = large if is_large else normal

        # 블록 상자 전체가 아니라 **글자가 실제로 놓인 줄 상자**만 본다.
        for run in block["runs"]:
            ratio, worst = worst_contrast_in_box(
                measurement.background_png_path,
                {"x": run["x"], "y": run["y"], "width": run["width"], "height": run["height"]},
                text_hex,
            )
            findings.append(
                ContrastFinding(
                    slide_index=measurement.index,
                    block_id=block["id"],
                    ratio=round(ratio, 2),
                    required=required,
                    text_color=text_hex,
                    worst_background=worst,
                )
            )
    return findings


def failing_contrast(measurement) -> list[ContrastFinding]:
    return [f for f in check_contrast(measurement) if not f.ok]
