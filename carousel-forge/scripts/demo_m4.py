#!/usr/bin/env python
"""M4 완료 기준: 스타일 + 주제 → 완성 캐러셀 1세트, 폐기·재생성 루프 동작.

    python scripts/demo_m2.py --keyword 러닝입문        # 구조 + 카피를 먼저 만든다
    export ANTHROPIC_API_KEY=...
    python scripts/demo_m4.py --keyword 러닝입문

배경 프로바이더는 기본이 `procedural`이다. 외부 크레딧 없이 루프 전체가 돌아야
버그를 먼저 잡을 수 있기 때문이다. 실제 생성물을 넣어 보려면 `--backgrounds
<디렉터리>`로 파일 프로바이더를 쓴다.

`--force-fail`은 품질 게이트가 반드시 폐기하도록 만들어 **재시도 소진 경로**를
실제로 밟는다. 통과하는 경우만 보고 루프가 돈다고 말할 수 없다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agents.base import AgentContext  # noqa: E402
from core.agents.quality_gate import Judgement, QualityGate, QualityReport  # noqa: E402
from core.config import STORAGE_DIR, platform_spec  # noqa: E402
from core.pipeline import ProductionFailed, SetProducer  # noqa: E402
from core.providers.image import FileProvider, ProceduralProvider  # noqa: E402
from core.render.model import Theme  # noqa: E402
from tests.fixtures.demo_set import demo_style_dna  # noqa: E402


class AlwaysDiscards(QualityGate):
    """지정한 슬라이드를 무조건 폐기하는 게이트.

    통과하는 경우만 보고 "폐기·재생성 루프가 돈다"고 말할 수 없다. 실패를
    주입해서 되감기·재생성·예산 소진까지 실제로 밟는다.
    """

    def __init__(self, *, targets: list[int] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.targets = targets      # None이면 전부

    def judge(self, *, measurements, **kwargs) -> QualityReport:
        return QualityReport(
            judgements=[
                Judgement(
                    rule_id="ai_text_artifact",
                    passed=self.targets is not None and m.index not in self.targets,
                    severity="blocking",
                    slide_index=m.index,
                    detector="vision",
                    reason=(
                        "강제 폐기 모드 — 재시도 소진 경로를 검증하기 위한 판정이다."
                        if self.targets is None or m.index in self.targets
                        else "강제 모드에서 대상이 아니라 통과시킨다."
                    ),
                )
                for m in measurements
            ]
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keyword", nargs="+", default=["러닝입문"])
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--state", type=Path, default=None, help="M2 상태 파일")
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "m4")
    ap.add_argument("--backgrounds", type=Path, default=None, help="미리 만든 배경 디렉터리")
    ap.add_argument("--no-vision", action="store_true", help="비전 판정을 끈다 (토큰 절약)")
    ap.add_argument("--force-fail", action="store_true", help="폐기·재시도 소진 경로를 밟는다")
    ap.add_argument(
        "--fail-slides", type=int, nargs="+", default=None,
        help="이 슬라이드만 폐기시킨다 (슬라이드 단위 재생성 루프 검증용)",
    )
    ap.add_argument(
        "--from-briefs",
        action="store_true",
        help="A7이 모델을 부르지 않고 A4의 visual_brief만으로 프롬프트를 짠다",
    )
    args = ap.parse_args()

    state_path = args.state or (STORAGE_DIR / "m2" / f"{'_'.join(args.keyword)}_state.json")
    if not state_path.exists():
        print(
            f"M2 상태가 없다: {state_path}\n"
            f"먼저 `python scripts/demo_m2.py --keyword {' '.join(args.keyword)}`를 실행하라.",
            file=sys.stderr,
        )
        return 2
    state = json.loads(state_path.read_text(encoding="utf-8"))

    dna = demo_style_dna()
    ctx = AgentContext(
        account_id="demo", platform=args.platform, language=args.language, style_dna=dna
    )
    spec = platform_spec(args.platform)
    theme = Theme.from_dna(dna, spec, spec.canvas)

    if args.backgrounds:
        provider = FileProvider.from_dir(args.backgrounds)
        print(f"배경: 파일 프로바이더 ({len(provider.paths)}장) — {args.backgrounds}")
    else:
        provider = ProceduralProvider(
            out_dir=args.out / "generated",
            top_color=theme.palette_primary if theme.overlay_type == "none" else theme.palette_background,
            bottom_color=theme.palette_background,
            text_zone=theme.text_zone,
            grain=max(0.03, theme.grain_intensity * 0.18),
        )
        print("배경: 절차적 생성 (외부 크레딧 없음)")

    forcing = args.force_fail or args.fail_slides
    gate = (
        AlwaysDiscards(targets=args.fail_slides, use_vision=False)
        if forcing
        else QualityGate(use_vision=not args.no_vision)
    )
    producer = SetProducer(
        ctx,
        provider,
        quality_gate=gate,
        set_id="m4demo",
        account="demo",
        use_briefs_only=args.from_briefs,
    )
    print(f"재시도 예산: 슬라이드당 {producer.budget.max_per_slide}회 · "
          f"세트 {producer.budget.max_per_set}회\n")

    try:
        result = producer.produce(
            state["outline"],
            state["copy"],
            work_dir=args.out / ".work",
            png_dir=args.out / "upload",
            background_dir=args.out / "backgrounds",
        )
    except ProductionFailed as exc:
        print("─" * 60)
        print("생산 실패 — 조용히 통과시키지 않았다")
        print("─" * 60)
        print(exc)
        print(f"\n시도 기록 {len(exc.log)}건:")
        for entry in exc.log:
            print(f"  {entry['attempt']}회 [{entry['stage']}] {entry['verdict']} "
                  f"슬라이드 {entry['slides']} ({entry['duration_ms']}ms)")
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "failure_log.json").write_text(
            json.dumps(exc.log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n기록 → {args.out / 'failure_log.json'}")
        return 1

    print("─" * 60)
    print(result.summary())
    print("─" * 60)

    print("\n배경 프롬프트 (6블록 구조):")
    for prompt in result.prompts[:3]:
        print(f"  {prompt.slide_index}. {prompt.prompt[:150]}…")
    print(f"  … 총 {len(result.prompts)}건. 네거티브 공통: {result.prompts[0].negative[:5]}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "production.json").write_text(
        json.dumps(
            {
                "attempts": [a.as_dict() for a in result.attempts],
                "discarded": result.discarded,
                "quality": result.quality.as_dict(),
                "adjustments": [a.describe() for a in result.composition.adjustments],
                "prompts": [
                    {"slide": p.slide_index, "prompt": p.prompt, "blocks": p.blocks}
                    for p in result.prompts
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n완성 세트 → {args.out / 'upload'}")
    print(f"생산 기록 → {args.out / 'production.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
