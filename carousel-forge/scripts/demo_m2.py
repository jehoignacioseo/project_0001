#!/usr/bin/env python
"""M2 완료 기준: 키워드 1개 → 슬라이드 구조 + 카피 JSON.

    export ANTHROPIC_API_KEY=...
    python scripts/demo_m2.py --keyword 러닝입문
    python scripts/demo_m2.py --keyword 러닝입문 --render   # M1 렌더까지 이어서

`--render`를 주면 M2가 만든 카피를 M1의 RenderSet에 그대로 실어 PNG/SVG/manifest까지
뽑는다. M2와 M1이 같은 CopyBlock 계약 위에서 맞물리는지 확인하는 것이 목적이다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agents import CopySmith, NarrativeArchitect, TopicIntake, check_outline  # noqa: E402
from core.agents.base import AgentContext  # noqa: E402
from core.config import STORAGE_DIR, platform_spec  # noqa: E402
from tests.fixtures.demo_set import demo_style_dna  # noqa: E402


def _banner(title: str) -> None:
    print(f"\n{'─' * 60}\n{title}\n{'─' * 60}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keyword", nargs="+", required=True, help="키워드 1~3개")
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--angle", type=int, default=None, help="각도 선택(0~2). 생략하면 자동")
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "m2")
    ap.add_argument("--render", action="store_true", help="M1 렌더까지 이어서 실행")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="앞 단계 결과가 저장돼 있으면 재사용한다 (개발 중 토큰 절약)",
    )
    args = ap.parse_args()

    dna = demo_style_dna()
    ctx = AgentContext(
        account_id="demo",
        platform=args.platform,
        language=args.language,
        style_dna=dna,
    )
    spec = platform_spec(args.platform)
    args.out.mkdir(parents=True, exist_ok=True)
    cache = args.out / f"{'_'.join(args.keyword)}_state.json"

    state = {"input_type": "keyword", "payload": args.keyword}
    if args.angle is not None:
        state["selected_angle_index"] = args.angle
    if args.resume and cache.exists():
        state = json.loads(cache.read_text(encoding="utf-8"))
        print(f"저장된 상태를 이어받는다: {cache}")

    _banner(f"A2 TopicIntake — 키워드 {args.keyword}")
    if "topic" not in state:
        state = TopicIntake().run(state, ctx)
        cache.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(" (저장된 결과 재사용)")
    for i, angle in enumerate(state["angle_proposals"]["angles"]):
        mark = "→" if i == state["selected_angle_index"] else " "
        print(f" {mark} [{i}] {angle['title']}\n      각도: {angle['angle']}\n      왜 지금: {angle['why_now']}")
    if state.get("angle_auto_selected"):
        print("   (자동 선택됨 — --angle로 바꿔 다시 돌릴 수 있다)")
    topic = state["topic"]
    print(f"\n 핵심 메시지: {topic['key_message']}")
    print(f" 근거 포인트 {len(topic['supporting_points'])}개")
    for p in topic["supporting_points"]:
        print(f"   · {p}")
    print(f" 검증 필요 주장 {len(topic['evidence_needed'])}개 (A6 FactChecker가 M5에서 검증)")
    for e in topic["evidence_needed"]:
        print(f"   ? {e}")
    print(f" source_fidelity: {topic['source_fidelity']}")

    _banner("A4 NarrativeArchitect — 구조 설계")
    if "outline" not in state:
        state = NarrativeArchitect().run(state, ctx)
        cache.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(" (저장된 결과 재사용)")
    outline = state["outline"]
    print(f" 슬라이드 {outline['slide_count']}장 · {outline['narrative_pattern']} · 훅 {outline['hook_type']}")
    print("\n 훅 후보 3개:")
    for i, h in enumerate(outline["hook_candidates"]):
        mark = "★" if i == outline["chosen_hook_index"] else " "
        print(f"  {mark} ({h['strength_score']:.2f}) {h['text']}")
        print(f"      {h['rationale']}")
    print("\n 슬라이드 골격:")
    for s in outline["slides"]:
        print(f"  {s['index']:>2}. [{s['role']:<8}] {s['single_message']}")

    problems = check_outline(outline, spec)
    print(f"\n 구조 검사: {'이상 없음' if not problems else ''}")
    for p in problems:
        print(f"   {p}")

    _banner("A5 CopySmith — 카피 생성 (StyleDNA 하드 제약)")
    state = CopySmith().run(state, ctx)
    cache.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    copy = state["copy"]
    print(f" 시도 횟수: {copy['attempts']}회")
    if copy["template_swaps"]:
        print(f" 템플릿 교체: {copy['template_swaps']}")
    for slide in copy["slides"]:
        print(f"\n  {slide['index']:>2}. [{slide['role']}] ({slide['layout_template']})")
        for b in slide["copy_blocks"]:
            shown = b["text"].replace("\n", " ⏎ ")
            print(f"      [{b['role']:<12}] {shown}  ({len(b['text'].replace(chr(10),''))}/{b['max_chars']}자)")

    print("\n 캡션:")
    print(f"   훅: {copy['caption']['hook_line']}")
    print(f"   본문: {copy['caption']['body'][:120]}...")
    print(f"   CTA: {copy['caption']['cta']}")
    print(f"   해시태그 {len(copy['hashtags'])}개: {' '.join(copy['hashtags'])}")
    for w in copy["warnings"]:
        print(f"   경고: {w}")

    out_path = args.out / f"{'_'.join(args.keyword)}.json"
    out_path.write_text(
        json.dumps(
            {"topic": topic, "outline": outline, "copy": copy}, ensure_ascii=False, indent=2
        ) + "\n",
        encoding="utf-8",
    )
    print(f"\n M2 산출물 → {out_path}")

    if args.render:
        _banner("M1 렌더 — M2 카피를 그대로 실어 PNG/SVG/manifest")
        from scripts.render_m2 import render_from_m2

        report = render_from_m2(state, ctx, out_root=STORAGE_DIR / "exports")
        print(report.summary())
        print(f"\n 내보내기 → {report.export_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
