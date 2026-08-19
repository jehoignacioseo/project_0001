#!/usr/bin/env python
"""M5(A6 FactChecker) — 출처 링크가 포함된 fact_report 생성.

    export ANTHROPIC_API_KEY=...
    python scripts/demo_m5.py

검색은 **Anthropic 서버에서 도는** web_search/web_fetch가 한다. 이 컨테이너의
아웃바운드가 조직 정책으로 막혀 있어도 검증이 되는 이유다.

`--claims`로 직접 주장을 넣거나, 생략하면 M2가 만든 상태 파일의 `evidence_needed`를
쓴다. 마지막에 카피의 숫자가 검증된 주장으로 덮이는지까지 확인한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agents import FactChecker  # noqa: E402
from core.agents.base import AgentContext  # noqa: E402
from core.config import STORAGE_DIR  # noqa: E402

DEFAULT_CLAIMS = [
    "인스타그램 캐러셀 게시물에는 사진이나 영상을 최대 20개까지 넣을 수 있다",
    "인스타그램 캡션은 최대 2,200자까지 쓸 수 있다",
    "인스타그램 피드에서 캡션은 약 125자 지점에서 접힌다",
    "샤오홍슈 게시물 제목은 20자를 넘으면 잘린다",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--claims", nargs="+", default=None, help="검증할 주장 (없으면 기본 목록)")
    ap.add_argument("--state", type=Path, default=None, help="M2 상태 파일에서 주장을 가져온다")
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "m5")
    args = ap.parse_args()

    copy = None
    if args.state and args.state.exists():
        state = json.loads(args.state.read_text(encoding="utf-8"))
        claims = args.claims or state["topic"].get("evidence_needed", [])
        copy = state.get("copy")
        print(f"상태 파일에서 주장 {len(claims)}건, 카피 {len(copy['slides'])}장을 읽었다")
    else:
        claims = args.claims or DEFAULT_CLAIMS

    ctx = AgentContext(account_id="demo", platform=args.platform, language=args.language)
    checker = FactChecker()
    print(f"주장 {len(claims)}건을 최대 {checker.max_parallel}개씩 병렬로 검증한다.")
    print("검색은 Anthropic 서버에서 돈다 — 이 컨테이너의 아웃바운드와 무관하다.\n")

    report = checker.check(claims=claims, copy=copy, ctx=ctx)

    print("─" * 60)
    print(report.summary())
    print("─" * 60)

    print("\n주장별 판정:")
    for check in report.claims:
        print(f"\n  [{check.verdict}] {check.claim}")
        print(f"    {check.reasoning[:220]}")
        for source in check.sources[:4]:
            print(f"    · {source.domain} — {source.url[:90]}")
        if not check.sources:
            print("    · 출처 없음")
        if check.unverified_urls:
            print(f"    ⚠ 검색이 열어 보지 않은 URL {len(check.unverified_urls)}건은 출처로 세지 않았다")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "fact_report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "fact_report.md").write_text(report.markdown(), encoding="utf-8")
    print(f"\n보고서 → {args.out / 'fact_report.md'}")

    if not report.passed:
        print("\n팩트체크를 통과하지 못했다. 파이프라인은 이 상태로 게시하지 않는다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
