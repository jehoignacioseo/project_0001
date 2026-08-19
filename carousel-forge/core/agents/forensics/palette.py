"""팔레트 추출 — k-means (k=6).

절대 규칙에 가까운 추출 규칙: **색상은 눈대중이 아니라 실제 픽셀 샘플링으로 뽑는다.**
비전 모델에게 "무슨 색이야?"라고 묻는 대신 픽셀을 직접 군집화한다. 모델의 색 인지는
조명·압축·주변색에 흔들리지만 픽셀은 흔들리지 않는다.

k-means는 초기값에 따라 결과가 달라지므로 k-means++ 초기화에 고정 시드를 쓴다.
같은 이미지를 넣으면 항상 같은 팔레트가 나와야 스타일이 재현 가능하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

K = 6
SEED = 20260819
MAX_ITERATIONS = 40
#: 큰 이미지를 전부 돌리면 느리다. 픽셀을 균등 표본으로 줄여도 군집 중심은 거의 같다.
MAX_SAMPLES = 60_000


@dataclass(frozen=True)
class Swatch:
    hex: str
    share: float          # 전체 픽셀 중 이 군집의 비중
    luminance: float      # WCAG 상대 명도

    @property
    def is_dark(self) -> bool:
        return self.luminance < 0.18


@dataclass(frozen=True)
class PaletteReport:
    swatches: tuple[Swatch, ...]
    #: 화면을 가장 많이 덮은 색 — 배경으로 본다
    background: Swatch
    #: 배경과 대비가 가장 큰 색 — 텍스트로 본다
    text: Swatch
    #: 비중은 작지만 배경과 확실히 구분되는 색 — 액센트로 본다
    accent: Swatch
    sampled_pixels: int

    def usage_ratio(self) -> dict[str, float]:
        """bg / primary / accent 비중. 합이 1이 되도록 정규화한다."""
        bg = self.background.share
        accent = self.accent.share
        primary = max(0.0, 1.0 - bg - accent)
        total = bg + accent + primary or 1.0
        return {
            "bg": round(bg / total, 3),
            "primary": round(primary / total, 3),
            "accent": round(accent / total, 3),
        }


def _relative_luminance(rgb: np.ndarray) -> float:
    channels = rgb / 255.0
    linear = np.where(channels <= 0.03928, channels / 12.92, ((channels + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2])


def _contrast(a: float, b: float) -> float:
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def load_pixels(path: Path) -> np.ndarray:
    """이미지를 (N, 3) uint8 배열로 읽는다."""
    from PIL import Image

    with Image.open(path) as img:
        rgb = img.convert("RGB")
        return np.asarray(rgb, dtype=np.uint8).reshape(-1, 3)


def _kmeans(points: np.ndarray, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """k-means++ 초기화 + Lloyd 반복. (중심, 각 점의 라벨)을 돌려준다."""
    data = points.astype(np.float64)
    n = len(data)
    k = min(k, n)

    # k-means++ — 첫 중심은 무작위, 이후는 기존 중심에서 먼 점일수록 뽑힐 확률이 높다.
    centres = np.empty((k, 3), dtype=np.float64)
    centres[0] = data[rng.integers(n)]
    closest = ((data - centres[0]) ** 2).sum(axis=1)
    for i in range(1, k):
        total = closest.sum()
        if total <= 0:
            centres[i] = data[rng.integers(n)]
        else:
            centres[i] = data[rng.choice(n, p=closest / total)]
        closest = np.minimum(closest, ((data - centres[i]) ** 2).sum(axis=1))

    labels = np.zeros(n, dtype=np.int64)
    for _ in range(MAX_ITERATIONS):
        distances = ((data[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for i in range(k):
            member = data[labels == i]
            if len(member):
                centres[i] = member.mean(axis=0)
    return centres, labels


def extract_palette(paths: list[Path], *, k: int = K) -> PaletteReport:
    """여러 장에서 하나의 팔레트를 뽑는다.

    피드 전체가 한 계정의 팔레트를 이루므로 이미지를 따로 돌리지 않고 픽셀을
    합쳐서 군집화한다. 그래야 "이 계정의 색"이 나온다.
    """
    if not paths:
        raise ValueError("팔레트를 뽑을 이미지가 없다")

    chunks = [load_pixels(p) for p in paths]
    pixels = np.concatenate(chunks, axis=0)

    rng = np.random.default_rng(SEED)
    if len(pixels) > MAX_SAMPLES:
        idx = rng.choice(len(pixels), size=MAX_SAMPLES, replace=False)
        pixels = pixels[idx]

    centres, labels = _kmeans(pixels, k, rng)
    counts = np.bincount(labels, minlength=len(centres))
    shares = counts / counts.sum()

    swatches = []
    for centre, share in zip(centres, shares, strict=True):
        rgb = np.clip(np.round(centre), 0, 255).astype(int)
        swatches.append(
            Swatch(
                hex="#{:02x}{:02x}{:02x}".format(*rgb),
                share=float(share),
                luminance=_relative_luminance(rgb.astype(float)),
            )
        )
    swatches.sort(key=lambda s: s.share, reverse=True)

    background = swatches[0]
    text = max(swatches[1:], key=lambda s: _contrast(s.luminance, background.luminance))

    # 액센트: 배경·텍스트가 아니면서, 배경과 충분히 구분되고 비중이 가장 큰 색.
    candidates = [
        s for s in swatches
        if s is not background and s is not text
        and _contrast(s.luminance, background.luminance) > 1.6
    ]
    accent = candidates[0] if candidates else text

    return PaletteReport(
        swatches=tuple(swatches),
        background=background,
        text=text,
        accent=accent,
        sampled_pixels=int(len(pixels)),
    )
