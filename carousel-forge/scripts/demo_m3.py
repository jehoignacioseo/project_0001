#!/usr/bin/env python
"""M3 완료 기준: 벤치마크 스크린샷 6장 → StyleDNA JSON + 검증 렌더.

    python scripts/make_benchmark_feed.py    # 정답을 아는 피드를 먼저 만든다
    export ANTHROPIC_API_KEY=...
    python scripts/demo_m3.py

정답 DNA로 만든 피드에서 다시 뽑으므로 **복원율을 숫자로 잴 수 있다.** 측정 층
(픽셀·기하·통계)이 틀리면 그건 버그고, 해석 층(모델)이 다르면 판단 차이다.
둘을 나눠서 보고한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agents import StyleForensics  # noqa: E402
from core.agents.base import AgentContext  # noqa: E402
from core.agents.forensics import compare_dna, render_verification  # noqa: E402
from core.config import STORAGE_DIR  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feed", type=Path, default=STORAGE_DIR / "benchmark" / "feed")
    ap.add_argument("--captions", type=Path, default=STORAGE_DIR / "benchmark" / "captions.json")
    ap.add_argument("--samples", type=int, default=6, help="스펙 최소치는 6장이다")
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "m3")
    ap.add_argument("--truth", type=Path, default=FIXTURES / "style_dna_benchmark.json")
    args = ap.parse_args()

    screenshots = sorted(args.feed.glob("*.png"))[: args.samples]
    if not screenshots:
        print(
            f"피드가 없다: {args.feed}\n먼저 `python scripts/make_benchmark_feed.py`를 실행하라.",
            file=sys.stderr,
        )
        return 2
    captions = (
        json.loads(args.captions.read_text(encoding="utf-8"))[: args.samples]
        if args.captions.exists()
        else []
    )

    ctx = AgentContext(account_id="benchmark", platform=args.platform, language=args.language)
    print(f"스크린샷 {len(screenshots)}장 · 캡션 {len(captions)}건으로 추출한다\n")

    result = StyleForensics().extract(screenshots, captions=captions, ctx=ctx)
    print(result.report())

    args.out.mkdir(parents=True, exist_ok=True)
    dna_path = args.out / "style_dna_extracted.json"
    dna_path.write_text(json.dumps(result.dna, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "report.txt").write_text(result.report() + "\n", encoding="utf-8")

    print(f"\n추출 DNA → {dna_path}")

    # ── 검증 렌더 (M3 필수) ────────────────────────────────────────────
    print("\n검증 렌더 — 더미 주제 3장을 뽑아 원본과 나란히 놓는다…")
    preview = render_verification(
        result.dna,
        originals=screenshots,
        out_dir=args.out,
        platform=args.platform,
        language=args.language,
    )
    print(f"  미리보기 {len(preview.preview_paths)}장 → {preview.preview_paths[0].parent}")
    print(f"  비교 시트 → {preview.comparison_path}")

    # ── 왕복 대조 ──────────────────────────────────────────────────────
    if args.truth.exists():
        truth = json.loads(args.truth.read_text(encoding="utf-8"))
        comparison = compare_dna(truth, result.dna)

        print("\n" + "═" * 58)
        print("  왕복 대조 — 정답 DNA 대비 복원율")
        print("═" * 58)
        print("\n[측정 층] 픽셀·기하·통계에서 잰 값 — 틀리면 버그다")
        for m in comparison.measured():
            print(f"  {m}")
        measured_ok = sum(m.ok for m in comparison.measured())
        print(f"  → {measured_ok}/{len(comparison.measured())}")

        print("\n[해석 층] 모델이 판단한 값 — 달라도 버그는 아니다")
        for m in comparison.interpreted():
            print(f"  {m}")
        interpreted_ok = sum(m.ok for m in comparison.interpreted())
        print(f"  → {interpreted_ok}/{len(comparison.interpreted())}")

        print(f"\n  전체 복원율 {comparison.score:.0%}")
        (args.out / "comparison.txt").write_text(str(comparison) + "\n", encoding="utf-8")

    print("\n다음 단계: 비교 시트를 보고 닮았다고 판단되면 활성화한다 (is_active=True).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
