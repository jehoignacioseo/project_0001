#!/usr/bin/env python
"""M1 검증용 더미 배경 생성기.

M1은 이미지 생성 프로바이더(A7 ArtDirector, M4) 없이 렌더 파이프라인만
검증한다. 그래서 배경은 여기서 절차적으로 만든다.

지켜야 할 것은 하나다 — **배경에는 글자가 없다.** 그레인이 섞인 그라디언트만
그린다. 외부 의존성 없이 zlib으로 PNG를 직접 쓴다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.config import platform_spec


# 구현은 프로바이더에 있다. 스크립트가 따로 들고 있으면 둘이 갈라진다.
from core.providers.image.procedural import gradient_background, write_png  # noqa: E402,F401

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
