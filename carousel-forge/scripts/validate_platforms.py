#!/usr/bin/env python
"""`config/platforms.yaml` 검증.

규격은 변한다. 빌드/CI에서 이 스크립트를 돌려 설정이 형태를 갖췄는지,
그리고 마지막 확인일이 너무 오래되지 않았는지 확인한다.

이 스크립트가 확인하지 **못하는** 것: 값 자체가 현재 플랫폼 정책과 맞는지.
그건 사람이 각 플랫폼 문서를 보고 갱신한 뒤 `_meta.verified_at`을 올려야 한다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import (  # noqa: E402
    STALE_AFTER,
    ConfigError,
    platform_keys,
    platform_spec,
    platforms_verified_at,
)

RATIO_TOLERANCE = 0.01


def check_platform(key: str) -> list[str]:
    problems: list[str] = []
    spec = platform_spec(key)

    for name, canvas in [("canvas", spec.canvas), *spec.alt_canvas.items()]:
        if canvas.width <= 0 or canvas.height <= 0:
            problems.append(f"{key}.{name}: 캔버스 크기가 양수가 아니다")
            continue
        try:
            w, h = (int(part) for part in canvas.ratio.split(":"))
        except ValueError:
            problems.append(f"{key}.{name}: ratio 표기가 'W:H'가 아니다 ({canvas.ratio})")
            continue
        declared = w / h
        actual = canvas.width / canvas.height
        if abs(declared - actual) > RATIO_TOLERANCE:
            problems.append(
                f"{key}.{name}: ratio {canvas.ratio}({declared:.3f})가 "
                f"실제 {canvas.width}×{canvas.height}({actual:.3f})와 다르다"
            )

    if spec.min_slides > spec.max_slides:
        problems.append(f"{key}: min_slides가 max_slides보다 크다")
    if spec.caption_fold_at > spec.caption_max_chars:
        problems.append(f"{key}: caption_fold_at이 caption_max_chars보다 크다")

    lo, hi = spec.hashtag_recommended
    if lo > hi:
        problems.append(f"{key}: hashtag_recommended 범위가 뒤집혀 있다")
    if hi > spec.hashtag_max:
        problems.append(f"{key}: hashtag_recommended 상한이 hashtag_max를 넘는다")

    # 안전영역이 캔버스의 절반을 넘으면 텍스트를 놓을 자리가 없다.
    if spec.safe_margin_px * 2 >= min(spec.canvas.width, spec.canvas.height):
        problems.append(f"{key}: safe_margin_px가 캔버스에 비해 너무 크다")

    if not spec.export_format:
        problems.append(f"{key}: export_format이 비어 있다")
    for fmt in spec.export_format:
        if fmt not in ("png", "jpg", "jpeg", "webp"):
            problems.append(f"{key}: 지원하지 않는 export_format {fmt!r}")
    if not 1 <= spec.quality <= 100:
        problems.append(f"{key}: quality는 1~100이어야 한다 (현재 {spec.quality})")
    if "{tag}" not in spec.topic_tag_format:
        problems.append(
            f"{key}: topic_tag_format에 '{{tag}}' 자리가 없다 — 모든 태그가 같은 "
            "문자열이 된다"
        )
    if spec.cover_min_blocks < 1:
        problems.append(f"{key}: cover_min_blocks는 1 이상이어야 한다")
    if not spec.culture_prompt:
        problems.append(
            f"{key}: culture_prompt가 비어 있다 — 플랫폼 문화 차이는 코드 주석이 아니라 "
            "프롬프트에 반영돼야 한다"
        )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()

    try:
        keys = platform_keys()
    except ConfigError as exc:
        print(f"설정을 읽을 수 없다: {exc}", file=sys.stderr)
        return 2

    problems: list[str] = []
    for key in keys:
        problems += check_platform(key)

    verified = platforms_verified_at()
    warnings: list[str] = []
    if verified is None:
        problems.append("_meta.verified_at이 없다. 규격을 언제 확인했는지 기록하라.")
    elif args.today - verified > STALE_AFTER:
        warnings.append(
            f"규격 확인일이 {verified}로 {(args.today - verified).days}일 지났다. "
            "각 플랫폼 문서를 다시 확인하고 _meta.verified_at을 갱신하라."
        )

    print(f"플랫폼 {len(keys)}개 검사: {', '.join(keys)}")
    for w in warnings:
        print(f"  경고: {w}")
    if problems:
        print("\n문제:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("  이상 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
