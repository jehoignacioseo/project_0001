"""절차적 배경 생성 — 외부 크레딧 없이 도는 기본 프로바이더.

이미지 모델이 없어도 파이프라인 전체(합성·품질 게이트·폐기·재생성)가 돌아야
한다. 그래야 루프 자체를 검증할 수 있고, 크레딧을 쓰기 전에 버그를 잡는다.

여기서 만드는 배경은 **글자가 없다.** 팔레트에서 뽑은 두 색의 그라디언트에
결정론적 그레인을 얹고, 텍스트가 얹힐 영역은 대비를 눌러 저정보 영역으로 비운다
— A7이 실제 이미지 모델에 요구하는 것과 같은 성질이다.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from core.providers.image.base import ImageProvider, ImageRequest, ImageResult


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, rows: list[bytearray]) -> None:
    """의존성 없이 PNG를 쓴다. 배경 생성에 이미지 라이브러리를 끌어올 이유가 없다."""
    raw = b"".join(b"\x00" + bytes(row) for row in rows)   # filter type 0
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _hex(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _grain(x: int, y: int, seed: int) -> int:
    """결정론적 의사난수. 같은 seed면 같은 그레인이 나와야 재현이 된다."""
    h = (x * 374_761_393 + y * 668_265_263 + seed * 2_246_822_519) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1_274_126_177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFF) - 128


#: text_zone → 대비를 눌러야 할 세로 구간 (시작, 끝) 비율
QUIET_BANDS: dict[str, tuple[float, float]] = {
    "top": (0.0, 0.45),
    "center": (0.3, 0.7),
    "bottom": (0.45, 1.0),
    "split": (0.0, 0.3),
    "full-bleed": (0.0, 1.0),
}


def gradient_background(
    width: int,
    height: int,
    top: str,
    bottom: str,
    *,
    seed: int,
    grain: float = 0.06,
    quiet_band: tuple[float, float] | None = (0.45, 1.0),
) -> list[bytearray]:
    """세로 그라디언트 + 그레인. `quiet_band` 구간은 저정보 영역으로 비운다."""
    tr, tg, tb = _hex(top)
    br, bg, bb = _hex(bottom)
    rows: list[bytearray] = []
    for y in range(height):
        t = y / max(height - 1, 1)
        base = (tr + (br - tr) * t, tg + (bg - tg) * t, tb + (bb - tb) * t)

        flatten = 0.0
        if quiet_band is not None:
            lo, hi = quiet_band
            if lo <= t <= hi:
                flatten = min(1.0, (t - lo) / max(hi - lo, 1e-6) * 1.4)

        row = bytearray()
        for x in range(width):
            noise = _grain(x, y, seed) * grain * (1.0 - 0.7 * flatten)
            for channel in base:
                value = int(round(channel + noise))
                row.append(0 if value < 0 else 255 if value > 255 else value)
        rows.append(row)
    return rows


@dataclass
class ProceduralProvider(ImageProvider):
    """팔레트에서 배경을 만든다. 외부 호출도 크레딧도 없다."""

    key: str = "procedural"
    out_dir: Path = Path("storage/assets/procedural")
    #: 팔레트에서 온 두 색. 없으면 중성 회색.
    top_color: str = "#1b1a17"
    bottom_color: str = "#0d0c0a"
    text_zone: str = "bottom"
    grain: float = 0.06
    #: 렌더 시 object-fit: cover로 늘어나므로 캔버스보다 작게 만들어도 된다.
    scale: int = 2

    def generate(self, request: ImageRequest) -> ImageResult:
        self.assert_no_text_request(request.prompt)

        seed = request.seed if request.seed is not None else abs(hash(request.prompt)) % 2**31
        width = max(1, request.width // self.scale)
        height = max(1, request.height // self.scale)
        rows = gradient_background(
            width,
            height,
            self.top_color,
            self.bottom_color,
            seed=seed,
            grain=self.grain,
            quiet_band=QUIET_BANDS.get(self.text_zone, QUIET_BANDS["full-bleed"]),
        )
        path = self.out_dir / f"bg_{seed:010d}.png"
        write_png(path, width, height, rows)

        return ImageResult(
            path=str(path),
            width=width,
            height=height,
            provider=self.key,
            seed=seed,
            prompt=request.prompt,
        )
