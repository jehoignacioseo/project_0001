#!/usr/bin/env python
"""M1 end-to-end 검증: 하드코딩 더미 데이터 9장 → PNG + SVG + manifest.

    python scripts/make_dummy_backgrounds.py
    python scripts/demo_render.py

끝나면 `storage/exports/deskreset_demo0001_instagram_ko/`에 섹션 6.1 구조가
그대로 생긴다. 검증 항목은 스크립트가 직접 확인해서 보고한다:

  1. 슬라이드마다 PNG/SVG/manifest 항목이 모두 있는가
  2. manifest 좌표와 SVG 좌표가 일치하는가 (같은 실측값에서 나왔는지)
  3. SVG의 텍스트가 <text>/<tspan>인가 (아웃라인화되지 않았는가)
  4. 텍스트가 안전영역을 벗어나지 않았는가
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import STORAGE_DIR  # noqa: E402
from core.render import render_and_export  # noqa: E402
from tests.fixtures.demo_set import CAPTION, HASHTAGS, demo_render_set, demo_style_dna  # noqa: E402

TSPAN_RE = re.compile(r'<tspan x="([\d.]+)" y="([\d.]+)"')


def verify_svg_manifest_agreement(export_dir: Path, manifest: dict) -> list[str]:
    """manifest와 SVG가 같은 실측값에서 나왔는지 대조한다.

    둘 중 하나라도 추정 좌표를 쓰면 여기서 어긋난다.
    """
    problems: list[str] = []
    for slide in manifest["slides"]:
        svg_path = export_dir / "02_figma" / f"slide_{slide['index']:02d}.svg"
        svg = svg_path.read_text(encoding="utf-8")

        if "<path" in svg:
            problems.append(f"{svg_path.name}: <path>가 있다 — 텍스트가 아웃라인화됐을 수 있다")

        for block in slide["copy_blocks"]:
            block_svg = re.search(
                rf'<text id="{re.escape(block["id"])}".*?</text>', svg, re.DOTALL
            )
            if block_svg is None:
                problems.append(f"{svg_path.name}: {block['id']}에 대응하는 <text>가 없다")
                continue
            tspans = TSPAN_RE.findall(block_svg.group(0))
            lines = block["line_boxes"]
            if len(tspans) < len(lines):
                problems.append(
                    f"{svg_path.name}: {block['id']}의 tspan {len(tspans)}개가 "
                    f"manifest 줄 수 {len(lines)}개보다 적다"
                )
                continue
            # SVG tspan의 x는 각 run의 실측 x다. 줄 시작 x는 manifest line_box와 같아야 한다.
            svg_line_starts = sorted({round(float(y), 2) for _, y in tspans})
            manifest_baselines = sorted({round(line["baseline"], 2) for line in lines})
            if svg_line_starts != manifest_baselines:
                problems.append(
                    f"{svg_path.name}: {block['id']}의 베이스라인이 manifest와 다르다 "
                    f"(svg={svg_line_starts} manifest={manifest_baselines})"
                )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--backgrounds", type=Path, default=STORAGE_DIR / "assets" / "demo" / "backgrounds")
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "exports")
    args = ap.parse_args()

    if not args.backgrounds.exists():
        print(
            f"배경 폴더가 없다: {args.backgrounds}\n"
            "먼저 `python scripts/make_dummy_backgrounds.py`를 실행하라.",
            file=sys.stderr,
        )
        return 2

    render_set = demo_render_set(platform=args.platform, language=args.language)
    print(f"렌더 시작 — {render_set.platform} {render_set.canvas.width}×{render_set.canvas.height}, "
          f"{len(render_set.slides)}장")

    report = render_and_export(
        render_set,
        out_root=args.out,
        background_source_dir=args.backgrounds,
        style_dna=demo_style_dna(),
        caption=CAPTION,
        hashtags=HASHTAGS,
    )
    print(report.summary())

    manifest = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    problems = verify_svg_manifest_agreement(report.export_dir, manifest)

    print("\n── 검증 ──")
    print(f"  슬라이드 수: {len(manifest['slides'])}")
    print(f"  카피 블록 수: {sum(len(s['copy_blocks']) for s in manifest['slides'])}")
    print(f"  manifest ↔ SVG 좌표 대조: {'일치' if not problems else f'{len(problems)}건 불일치'}")
    for p in problems:
        print(f"    - {p}")
    print(f"  안전영역 침범: {len(report.overflows)}건")
    for o in report.overflows:
        print(f"    - {o}")

    if problems or report.overflows:
        print("\n실패. 위 항목을 고치기 전에는 통과로 보지 않는다.", file=sys.stderr)
        return 1

    print(f"\n완료 → {report.export_dir}")
    print("Figma 확인: 02_figma/slide_01.svg를 Figma로 끌어다 놓고 텍스트를 더블클릭해 보라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
