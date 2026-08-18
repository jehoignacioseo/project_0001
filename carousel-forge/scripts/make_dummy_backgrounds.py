#!/usr/bin/env python
"""M1 검증용 더미 배경 생성기.

M1은 이미지 생성 프로바이더(A7 ArtDirector, M4) 없이 렌더 파이프라인만
검증한다. 그래서 배경은 여기서 절차적으로 만든다.

지켜야 할 것은 하나다 — **배경에는 글자가 없다.** 그레인이 섞인 그라디언트만
그린다. 외부 의존성 없이 zlib으로 PNG를 직접 쓴다.
"""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from core.config import platform_spec


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, rows: list[bytearray]) -> None:
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
    """결정적 의사난수 그레인. 필름 그레인 느낌만 내면 되므로 가볍게 간다."""
    h = (x * 374_761_393 + y * 668_265_263 + seed * 2_246_822_519) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1_274_126_177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFF) - 128


def gradient_background(
    width: int,
    height: int,
    top: str,
    bottom: str,
    *,
    seed: int,
    grain: float = 0.06,
    low_detail_zone: tuple[float, float] | None = (0.45, 1.0),
) -> list[bytearray]:
    """세로 그라디언트 + 그레인.

    `low_detail_zone`은 텍스트가 얹힐 영역이다. 그 구간은 대비를 눌러
    저정보 영역으로 비워 둔다 — A7 ArtDirector가 실제 이미지에 요구하는 것과
    같은 성질을 더미에서도 지킨다.
    """
    tr, tg, tb = _hex(top)
    br, bg, bb = _hex(bottom)
    rows: list[bytearray] = []
    for y in range(height):
        t = y / max(height - 1, 1)
        base = (
            tr + (br - tr) * t,
            tg + (bg - tg) * t,
            tb + (bb - tb) * t,
        )
        flatten = 0.0
        if low_detail_zone is not None:
            lo, hi = low_detail_zone
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


PALETTES = [
    ("#1b1a17", "#0d0c0a"),
    ("#2a2622", "#12100e"),
    ("#1f2320", "#0c0e0d"),
    ("#241d1a", "#100b09"),
    ("#1a1f26", "#0a0d10"),
    ("#26201c", "#100c0a"),
    ("#1d1c22", "#0b0a0e"),
    ("#221e1a", "#0e0c0a"),
    ("#171a1c", "#08090a"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("storage/assets/demo/backgrounds"))
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--count", type=int, default=9)
    ap.add_argument(
        "--scale",
        type=int,
        default=2,
        help="캔버스 대비 축소 배수. 배경은 object-fit: cover로 늘어나므로 작아도 된다.",
    )
    args = ap.parse_args()

    canvas = platform_spec(args.platform).canvas
    width, height = canvas.width // args.scale, canvas.height // args.scale

    for i in range(1, args.count + 1):
        top, bottom = PALETTES[(i - 1) % len(PALETTES)]
        rows = gradient_background(width, height, top, bottom, seed=i * 7919)
        path = args.out / f"bg_{i:02d}.png"
        write_png(path, width, height, rows)
        print(f"  {path} ({width}×{height})")

    print(f"더미 배경 {args.count}장 생성 완료. 배경에 글자는 없다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
