"""StyleDNA 대조 — 추출 결과가 정답에 얼마나 가까운가.

두 곳에서 쓴다.
  1. M3 왕복 검증 — 알려진 DNA로 만든 피드에서 다시 뽑았을 때 얼마나 복원되는가
  2. A9 QualityGate의 `style_deviation` (M4) — 만들어진 결과물이 DNA를 얼마나 벗어났는가

색 거리는 CIEDE2000을 쓴다. RGB 유클리드 거리는 사람 눈의 민감도와 어긋나서,
어두운 색끼리의 큰 차이를 작게, 밝은 색끼리의 작은 차이를 크게 잡는다.
임계값은 `config/quality_rules.yaml`의 `style_deviation.palette_delta_e_max`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from core.config import quality_rules


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_lab(value: str) -> tuple[float, float, float]:
    """sRGB hex → CIELAB (D65)."""
    v = value.lstrip("#")
    r, g, b = (_srgb_to_linear(int(v[i : i + 2], 16) / 255) for i in (0, 2, 4))

    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy) - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e_2000(hex_a: str, hex_b: str) -> float:
    """CIEDE2000 색차. 대략 1 이하면 눈으로 구분하기 어렵고, 10 이상이면 확연히 다르다."""
    l1, a1, b1 = hex_to_lab(hex_a)
    l2, a2, b2 = hex_to_lab(hex_b)

    avg_l = (l1 + l2) / 2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    avg_c = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(avg_c**7 / (avg_c**7 + 25**7))) if avg_c > 0 else 0.0

    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    avg_cp = (c1p + c2p) / 2

    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)

    if c1p * c2p == 0:
        avg_hp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        avg_hp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        avg_hp = (h1p + h2p + 360) / 2
    else:
        avg_hp = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(avg_hp - 30))
        + 0.24 * math.cos(math.radians(2 * avg_hp))
        + 0.32 * math.cos(math.radians(3 * avg_hp + 6))
        - 0.20 * math.cos(math.radians(4 * avg_hp - 63))
    )
    sl = 1 + (0.015 * (avg_l - 50) ** 2) / math.sqrt(20 + (avg_l - 50) ** 2)
    sc = 1 + 0.045 * avg_cp
    sh = 1 + 0.015 * avg_cp * t
    rt = (
        -2
        * math.sqrt(avg_cp**7 / (avg_cp**7 + 25**7))
        * math.sin(math.radians(60 * math.exp(-(((avg_hp - 275) / 25) ** 2))))
        if avg_cp > 0
        else 0.0
    )
    return math.sqrt(
        (dlp / sl) ** 2 + (dcp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dcp / sc) * (dHp / sh)
    )


@dataclass(frozen=True)
class FieldMatch:
    field: str
    expected: Any
    actual: Any
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        mark = "✓" if self.ok else "✗"
        tail = f"  ({self.detail})" if self.detail else ""
        return f"{mark} {self.field:<34} {self.expected!s:<22} → {self.actual!s}{tail}"


@dataclass
class DnaComparison:
    matches: list[FieldMatch]

    @property
    def score(self) -> float:
        return sum(m.ok for m in self.matches) / len(self.matches) if self.matches else 0.0

    def measured(self) -> list[FieldMatch]:
        """픽셀·기하·통계에서 잰 필드 — 여기가 틀리면 측정 층의 버그다."""
        return [m for m in self.matches if m.field.startswith(("palette.", "layout.", "copy."))]

    def interpreted(self) -> list[FieldMatch]:
        """모델이 해석한 필드 — 틀려도 측정 버그는 아니고 판단 차이다."""
        return [m for m in self.matches if m not in self.measured()]

    def __str__(self) -> str:
        return "\n".join(str(m) for m in self.matches)


def _num(field: str, expected: float, actual: float, tolerance: float) -> FieldMatch:
    delta = abs(expected - actual)
    return FieldMatch(
        field, round(expected, 4), round(actual, 4), delta <= tolerance, f"차이 {delta:.4f}"
    )


def _colour(field: str, expected: str, actual: str, limit: float) -> FieldMatch:
    delta = delta_e_2000(expected, actual)
    return FieldMatch(field, expected, actual, delta <= limit, f"ΔE {delta:.1f}")


def _exact(field: str, expected: Any, actual: Any) -> FieldMatch:
    return FieldMatch(field, expected, actual, expected == actual)


def compare_dna(expected: dict[str, Any], actual: dict[str, Any]) -> DnaComparison:
    """정답 DNA와 추출 DNA를 필드별로 대조한다."""
    thresholds = quality_rules()["thresholds"]["style_deviation"]
    delta_e_max = float(thresholds["palette_delta_e_max"])
    ratio_tolerance = float(thresholds["font_size_ratio_tolerance"])

    ev, av = expected["visual"], actual["visual"]
    ep, ap = ev["palette"], av["palette"]
    et, at = ev["typography"], av["typography"]
    el, al = ev["layout"], av["layout"]
    es, as_ = expected["structure"], actual["structure"]
    ec, ac = expected["copy"], actual["copy"]

    matches = [
        _colour("palette.background", ep["background"][0], ap["background"][0], delta_e_max),
        _colour("palette.text", ep["text"][0], ap["text"][0], delta_e_max),
        _colour("palette.accent", ep["accent"][0], ap["accent"][0], delta_e_max),
        _exact("layout.text_zone", el["text_zone"], al["text_zone"]),
        _exact("layout.alignment", el["alignment"], al["alignment"]),
        _num("layout.safe_margin_ratio", el["safe_margin_ratio"], al["safe_margin_ratio"], 0.03),
        # size_ratio는 상대 허용치를 쓴다 — 0.072와 0.09는 절대차는 작아도 체감은 크다.
        _num(
            "typography.headline.size_ratio",
            et["headline"]["size_ratio"],
            at["headline"]["size_ratio"],
            et["headline"]["size_ratio"] * ratio_tolerance,
        ),
        _num(
            "typography.body.size_ratio",
            et["body"]["size_ratio"],
            at["body"]["size_ratio"],
            et["body"]["size_ratio"] * ratio_tolerance,
        ),
        _exact("copy.register", ec["register"], ac["register"]),
        _num("copy.emoji_density", ec["emoji_density"], ac["emoji_density"], 0.02),
        _num(
            "caption.hashtag_count",
            expected["caption"]["hashtag_strategy"]["count"],
            actual["caption"]["hashtag_strategy"]["count"],
            1,
        ),
        _exact("identity.archetype", expected["identity"]["archetype"], actual["identity"]["archetype"]),
        _exact("structure.narrative_pattern", es["narrative_pattern"], as_["narrative_pattern"]),
        _exact("structure.hook_type", es["hook_type"], as_["hook_type"]),
        _exact("structure.cta_type", es["cta_type"], as_["cta_type"]),
        _exact("structure.cover_rule", es["cover_rule"], as_["cover_rule"]),
    ]
    return DnaComparison(matches=matches)
