"""텍스트 영역 기하 분석.

카피가 화면 어디에 놓이는지(text_zone), 여백을 얼마나 두는지(safe_margin_ratio),
정렬이 어느 쪽인지(alignment)는 **재면 나오는 값**이다.

글자를 읽을 필요는 없다. 글자가 있는 곳은 국소 대비가 급격히 오르므로, 인접
픽셀과의 차이(경사)를 재면 텍스트가 놓인 띠가 드러난다. OCR 없이도 위치와
비율은 충분히 정확하게 잡힌다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: 경사 에너지가 이 분위수를 넘는 행/열을 "잉크가 있는 곳"으로 본다.
INK_QUANTILE = 0.82
#: 분위수만 쓰면 안 된다 — 여백이 많은 장에서는 82% 분위수가 0이 되고, 그러면
#: `energy >= 0`이 전부 참이라 **빈 화면 전체가 글자로 읽힌다**. 최대 에너지 대비
#: 하한을 함께 두어, 실제로 튀는 곳만 잉크로 센다.
INK_RELATIVE = 0.12
#: 최대 에너지가 이보다 작으면 대비가 없는 장이다 — 글자가 없다고 본다.
INK_FLOOR = 0.5
#: 잉크 행이 전체의 이 비율 미만이면 텍스트가 거의 없는 장으로 본다.
MIN_INK_ROWS = 0.02


@dataclass(frozen=True)
class ZoneReport:
    text_zone: str            # top | center | bottom | split | full-bleed
    safe_margin_ratio: float  # 캔버스 짧은 변 대비
    alignment: str            # left | center | justified
    ink_top: float            # 텍스트 띠의 시작 (0~1, 위에서부터)
    ink_bottom: float
    ink_coverage: float       # 잉크가 있는 행의 비율 — 정보 밀도의 대리 지표
    samples: int

    @property
    def cover_info_density(self) -> str:
        return "high" if self.ink_coverage > 0.28 else "low"


def _gradient_energy(gray: np.ndarray) -> np.ndarray:
    """인접 픽셀과의 차이. 글자 가장자리에서 크게 튄다."""
    dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1]))
    dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    return dy + dx


def _load_gray(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as img:
        # 세로 512로 줄여도 텍스트 띠의 위치 비율은 유지된다. 계산은 훨씬 싸진다.
        w, h = img.size
        scale = 512 / max(h, 1)
        resized = img.convert("L").resize((max(1, int(w * scale)), 512))
        return np.asarray(resized, dtype=np.float64)


def _line_bands(energy: np.ndarray, row_threshold: float) -> list[tuple[int, int]]:
    """잉크가 이어지는 행 구간 = 글줄. 줄 단위로 봐야 정렬을 알 수 있다."""
    ink = energy.mean(axis=1) >= row_threshold
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, on in enumerate(ink):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= 3:          # 3행 미만은 노이즈로 본다
                bands.append((start, i))
            start = None
    if start is not None and len(ink) - start >= 3:
        bands.append((start, len(ink)))
    return bands


#: 가장 긴 줄의 이 비율 이상인 줄만 정렬 판정에 쓴다.
#: 뱃지·라벨 같은 짧은 조각은 본문과 정렬이 다른 경우가 흔해서, 같은 무게로
#: 세면 긴 줄이 말하는 정렬이 묻힌다.
LONG_LINE_RATIO = 0.5


def _alignment_from_bands(
    energy: np.ndarray, bands: list[tuple[int, int]], col_threshold: float
) -> tuple[str, float]:
    """줄마다 좌우 끝을 재서 정렬을 판정한다.

    전체 이미지의 잉크 범위만 보면 왼쪽 뱃지 + 가운데 정렬 헤드라인처럼 섞인
    레이아웃을 왼쪽 정렬로 잘못 읽는다. 줄마다 재서, **왼쪽 끝이 일정한지**와
    **중심이 일정한지** 중 어느 쪽 흔들림이 작은지로 가린다.
    """
    lines: list[tuple[float, float, float]] = []   # (left, centre, span)
    width = energy.shape[1]
    for top, bottom in bands:
        cols = energy[top:bottom].mean(axis=0)
        ink = np.flatnonzero(cols >= col_threshold)
        if len(ink) < 2:
            continue
        left, right = ink[0] / width, ink[-1] / width
        lines.append((left, (left + right) / 2, right - left))

    if len(lines) < 2:
        return "left", 0.0

    longest = max(line[2] for line in lines)
    long_lines = [line for line in lines if line[2] >= longest * LONG_LINE_RATIO]
    if len(long_lines) < 2:
        long_lines = lines

    spans = np.array([line[2] for line in long_lines])
    # 줄 길이가 고르면 어느 쪽으로도 정렬돼 보인다. 그럴 땐 판정하지 않는다.
    if float(spans.std()) < 0.02:
        return "left", 0.0

    left_spread = float(np.std([line[0] for line in long_lines]))
    centre_spread = float(np.std([line[1] for line in long_lines]))
    # strength는 항상 확신의 크기다. 부호를 그대로 넘기면 투표가 뒤집힌다.
    strength = abs(left_spread - centre_spread)
    return ("center", strength) if centre_spread < left_spread else ("left", strength)


def analyse_text_zones(paths: list[Path]) -> ZoneReport:
    if not paths:
        raise ValueError("분석할 이미지가 없다")

    tops, bottoms, coverages, margins = [], [], [], []
    alignment_votes: dict[str, float] = {"left": 0.0, "center": 0.0}

    for path in paths:
        gray = _load_gray(path)
        energy = _gradient_energy(gray)

        row_energy = energy.mean(axis=1)
        col_energy = energy.mean(axis=0)
        if row_energy.max() < INK_FLOOR:
            continue                    # 대비가 없다 = 글자가 없다
        row_threshold = max(
            float(np.quantile(row_energy, INK_QUANTILE)), float(row_energy.max()) * INK_RELATIVE
        )
        col_threshold = max(
            float(np.quantile(col_energy, INK_QUANTILE)), float(col_energy.max()) * INK_RELATIVE
        )

        ink_rows = np.flatnonzero(row_energy >= row_threshold)
        if len(ink_rows) < len(row_energy) * MIN_INK_ROWS:
            continue

        height = len(row_energy)
        tops.append(ink_rows[0] / height)
        bottoms.append(ink_rows[-1] / height)
        coverages.append(len(ink_rows) / height)

        ink_cols = np.flatnonzero(col_energy >= col_threshold)
        width = len(col_energy)
        left, right = ink_cols[0] / width, ink_cols[-1] / width
        # 안전영역은 **가장 넓게 뻗은 줄**이 결정한다. 가운데 정렬이면 대부분의
        # 줄이 여백을 남기므로, 중앙값을 쓰면 실제 여백보다 크게 잡힌다.
        margins.append(min(left, 1.0 - right))

        bands = _line_bands(energy, row_threshold)
        verdict, strength = _alignment_from_bands(energy, bands, col_threshold)
        alignment_votes[verdict] += strength

    if not tops:
        # 텍스트가 잡히지 않았다. 추정해서 넘어가지 않고 그대로 알린다.
        return ZoneReport(
            text_zone="full-bleed",
            safe_margin_ratio=0.08,
            alignment="left",
            ink_top=0.0,
            ink_bottom=1.0,
            ink_coverage=0.0,
            samples=0,
        )

    top = float(np.median(tops))
    bottom = float(np.median(bottoms))
    centre = (top + bottom) / 2
    span = bottom - top

    if span > 0.75:
        zone = "full-bleed"
    elif span > 0.55:
        zone = "split"
    elif centre < 0.4:
        zone = "top"
    elif centre > 0.62:
        zone = "bottom"
    else:
        zone = "center"

    alignment = "center" if alignment_votes["center"] > alignment_votes["left"] else "left"

    return ZoneReport(
        text_zone=zone,
        # 계정의 안전영역은 **가장 넓게 뻗은 장**이 드러낸다. 나머지 장은
        # 카피가 짧아 여백이 더 커 보일 뿐이므로 중앙값을 쓰면 과대평가된다.
        safe_margin_ratio=round(float(min(margins)), 4),
        alignment=alignment,
        ink_top=round(top, 4),
        ink_bottom=round(bottom, 4),
        ink_coverage=round(float(np.median(coverages)), 4),
        samples=len(tops),
    )
