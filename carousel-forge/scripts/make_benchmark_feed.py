#!/usr/bin/env python
"""M3 검증용 벤치마크 피드 생성.

A1을 제대로 검증하려면 **정답을 아는 피드**가 필요하다. 실제 계정 스크린샷은
정답이 없고(그 계정의 진짜 DNA를 우리가 알 수 없다) 남의 저작물이기도 하다.

그래서 알려진 StyleDNA로 우리 렌더러가 피드를 만들고, A1이 그것만 보고 DNA를
얼마나 복원하는지 잰다. 왕복이 닫히므로 추출 정확도를 숫자로 말할 수 있다.

    python scripts/make_benchmark_feed.py
    python scripts/demo_m3.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import STORAGE_DIR, platform_spec  # noqa: E402
from core.render.html_renderer import SlideRenderer  # noqa: E402
from core.render.model import RenderBlock, RenderSet, RenderSlide, Theme  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

#: 이 계정의 게시물 8건. 각 건의 커버 한 장씩이 피드에 보이는 셈이다.
POSTS: list[dict] = [
    {
        "badge": "고정비 점검",
        "headline": "통신비, 3년째\n같은 요금제 쓰고 계신가요?",
        "sub": "평균 월 1만 8천원이 그냥 나갑니다",
        "caption": "통신비, 마지막으로 확인하신 게 언제인가요?\n\n"
                   "3년 전 요금제를 그대로 쓰고 계신 분이 정말 많습니다. "
                   "데이터는 남는데 요금은 그대로인 경우죠. ✨\n\n"
                   "오늘 바로 사용량부터 확인해 보세요!\n\n"
                   "#통신비절약 #고정비줄이기 #가계부 #알뜰폰 #요금제변경 "
                   "#사회초년생 #재테크기초 #돈관리 #생활비절약",
    },
    {
        "badge": "구독 정리",
        "headline": "안 쓰는 구독,\n몇 개나 남아 있을까요?",
        "sub": "평균 4.2개가 방치되고 있습니다",
        "caption": "구독 서비스, 몇 개나 결제되고 계신가요?\n\n"
                   "카드 명세서를 펼치면 기억에 없는 항목이 꼭 나옵니다. "
                   "한 달에 한 번만 봐도 새는 돈이 보입니다. 💡\n\n"
                   "오늘 바로 명세서를 열어 확인해 보세요!\n\n"
                   "#구독정리 #고정비줄이기 #가계부 #자동결제 #소비점검 "
                   "#사회초년생 #돈관리 #생활비절약 #재테크기초",
    },
    {
        "badge": "카드 혜택",
        "headline": "실적 못 채우는 카드는\n오히려 손해입니다",
        "sub": "연회비만 나가고 혜택은 0원",
        "caption": "카드 실적, 매달 채우고 계신가요?\n\n"
                   "실적을 못 채우면 연회비만 나갑니다. "
                   "카드 수를 줄이는 게 혜택을 늘리는 길일 때가 많습니다.\n\n"
                   "오늘 바로 실적 조건을 확인해 보세요! ✨\n\n"
                   "#카드혜택 #연회비 #고정비줄이기 #가계부 #신용카드정리 "
                   "#사회초년생 #돈관리 #재테크기초 #생활비절약",
    },
    {
        "badge": "보험 점검",
        "headline": "중복 보장,\n두 번 내고 계실 수 있습니다",
        "sub": "실손은 하나면 충분합니다",
        "caption": "보험 증권, 마지막으로 열어 보신 게 언제인가요?\n\n"
                   "실손이 두 개면 보장은 하나만 받고 보험료는 두 번 냅니다. "
                   "중복부터 정리하는 게 순서입니다. 💡\n\n"
                   "오늘 바로 증권을 확인해 보세요!\n\n"
                   "#보험점검 #실손보험 #중복보장 #고정비줄이기 #가계부 "
                   "#사회초년생 #돈관리 #재테크기초 #생활비절약",
    },
    {
        "badge": "자동이체",
        "headline": "월급날 다음 날,\n자동이체를 걸어 두세요",
        "sub": "남는 돈을 모으면 남지 않습니다",
        "caption": "저축, 남는 돈으로 하고 계신가요?\n\n"
                   "남는 돈은 좀처럼 남지 않습니다. 월급 들어온 다음 날 "
                   "먼저 빠져나가게 걸어 두는 편이 확실합니다. ✨\n\n"
                   "오늘 바로 이체일을 옮겨 보세요!\n\n"
                   "#자동이체 #선저축 #가계부 #고정비줄이기 #저축습관 "
                   "#사회초년생 #돈관리 #재테크기초 #생활비절약",
    },
    {
        "badge": "배달비",
        "headline": "배달비 3천원이\n한 달이면 얼마일까요?",
        "sub": "주 3회면 연 46만원입니다",
        "caption": "배달비, 한 번에 얼마씩 내고 계신가요?\n\n"
                   "한 건은 작아 보이지만 주 3회면 연 단위로는 꽤 큰 돈이 됩니다. "
                   "횟수를 줄이는 것만으로도 차이가 납니다.\n\n"
                   "오늘 바로 이번 달 배달 내역을 확인해 보세요! 💡\n\n"
                   "#배달비 #생활비절약 #가계부 #소비점검 #식비줄이기 "
                   "#사회초년생 #돈관리 #재테크기초 #고정비줄이기",
    },
    {
        "badge": "공과금",
        "headline": "관리비 고지서,\n항목별로 보신 적 있나요?",
        "sub": "세대별 항목에서 차이가 납니다",
        "caption": "관리비 고지서, 총액만 보고 계신가요?\n\n"
                   "항목별로 펼쳐 보면 우리 집만 유독 높은 줄이 보입니다. "
                   "거기서부터 줄이면 됩니다. ✨\n\n"
                   "오늘 바로 이번 달 고지서를 확인해 보세요!\n\n"
                   "#관리비 #공과금 #생활비절약 #가계부 #고정비줄이기 "
                   "#사회초년생 #돈관리 #재테크기초 #소비점검",
    },
    {
        "badge": "정리 순서",
        "headline": "줄이는 순서가\n결과를 바꿉니다",
        "sub": "고정비 먼저, 변동비는 나중에",
        "caption": "지출을 줄일 때 어디부터 손대고 계신가요?\n\n"
                   "변동비부터 조이면 오래 못 갑니다. 한 번 줄이면 계속 유지되는 "
                   "고정비부터 손대는 편이 훨씬 편합니다. 💡\n\n"
                   "오늘 바로 고정비 목록을 확인해 보세요!\n\n"
                   "#고정비줄이기 #가계부 #지출관리 #생활비절약 #소비점검 "
                   "#사회초년생 #돈관리 #재테크기초 #저축습관",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "benchmark")
    ap.add_argument("--platform", default="instagram")
    ap.add_argument("--count", type=int, default=len(POSTS))
    args = ap.parse_args()

    dna = json.loads((FIXTURES / "style_dna_benchmark.json").read_text(encoding="utf-8"))
    spec = platform_spec(args.platform)
    theme = Theme.from_dna(dna, spec, spec.canvas)
    posts = POSTS[: args.count]

    slides = []
    for i, post in enumerate(posts, start=1):
        slides.append(
            RenderSlide(
                index=i,
                role="hook",
                background_fill=theme.palette_background,
                blocks=[
                    RenderBlock(id=f"s{i:02d}_badge", role="badge", text=post["badge"]),
                    RenderBlock(id=f"s{i:02d}_headline", role="headline", text=post["headline"]),
                    RenderBlock(id=f"s{i:02d}_subhead", role="subhead", text=post["sub"]),
                ],
            )
        )

    render_set = RenderSet(
        set_id="benchmark",
        account="moneyfix",
        platform=args.platform,
        language="ko",
        theme=theme,
        slides=slides,
    )

    feed_dir = args.out / "feed"
    SlideRenderer().render_set(
        render_set,
        work_dir=args.out / ".work",
        png_dir=feed_dir,
        image_format="png",
    )
    (args.out / "captions.json").write_text(
        json.dumps([p["caption"] for p in posts], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"벤치마크 피드 {len(posts)}장 → {feed_dir}")
    print(f"캡션 {len(posts)}건 → {args.out / 'captions.json'}")
    print(f"정답 DNA: {FIXTURES / 'style_dna_benchmark.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
