"""M1 end-to-end 검증용 하드코딩 더미 세트 (9장).

카피는 손으로 적은 것이다. A5 CopySmith(M2)가 붙기 전까지 렌더 파이프라인만
검증하기 위한 고정 데이터이며, 여기 있는 숫자·주장은 팩트체크를 거치지 않았다.
실제 세트에서는 A6 FactChecker(M5)를 통과하지 않은 숫자는 출력되지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.config import platform_spec
from core.render.model import RenderBlock, RenderSet, RenderSlide, Theme

FIXTURES = Path(__file__).parent
DEMO_DNA_PATH = FIXTURES / "style_dna_demo.json"

CAPTION = {
    "hook_line": "책상을 바꾸면 집중이 바뀝니다. 오늘 저녁에 끝낼 수 있는 9가지.",
    "body": (
        "장비를 새로 사는 이야기가 아닙니다.\n"
        "이미 가지고 있는 것의 위치와 밝기를 바꾸는 이야기예요.\n\n"
        "저는 이 순서대로 정리하고 나서, 앉자마자 일이 시작되는 감각을 되찾았어요."
    ),
    "cta": "나중에 다시 볼 수 있게 저장해두세요.",
}

HASHTAGS = [
    "#데스크셋업", "#책상정리", "#홈오피스", "#작업환경", "#집중력",
    "#워크스페이스", "#데스크테리어", "#생산성", "#미니멀데스크", "#재택근무",
    "#공간정리", "#루틴만들기",
]

#: (role, 배경, 블록들)
_SLIDES: list[tuple[str, str, list[dict]]] = [
    (
        "hook", "bg_01.png",
        [
            {"id": "s01_eyebrow", "role": "eyebrow", "text": "DESK RESET"},
            {"id": "s01_headline", "role": "headline",
             "text": "집중이 끊기는 건\n의지가 아니라 책상 탓이에요",
             "max_chars": 40, "emphasis_spans": [(10, 12)]},
            {"id": "s01_subhead", "role": "subhead", "text": "오늘 저녁에 끝낼 수 있는 9가지"},
        ],
    ),
    (
        "context", "bg_02.png",
        [
            {"id": "s02_badge", "role": "badge", "text": "왜"},
            {"id": "s02_headline", "role": "headline", "text": "손이 먼저 멈추는\n지점을 찾으세요", "max_chars": 30},
            {"id": "s02_body", "role": "body",
             "text": "앉아서 일을 시작하기까지 몇 번 손이 멈추는지 세어보세요.\n그 지점이 전부 고칠 곳이에요.",
             "max_chars": 80},
        ],
    ),
    (
        "point", "bg_03.png",
        [
            {"id": "s03_badge", "role": "badge", "text": "01"},
            {"id": "s03_headline", "role": "headline", "text": "모니터는\n눈높이보다 살짝 아래", "max_chars": 24},
            {"id": "s03_body", "role": "body",
             "text": "화면 상단이 눈높이에 오도록 올리면 목이 앞으로 빠지지 않아요.",
             "max_chars": 80},
        ],
    ),
    (
        "point", "bg_04.png",
        [
            {"id": "s04_badge", "role": "badge", "text": "02"},
            {"id": "s04_headline", "role": "headline", "text": "조명은 화면 뒤가 아니라\n옆에서", "max_chars": 24},
            {"id": "s04_body", "role": "body",
             "text": "화면 뒤 창은 눈을 계속 조이게 만들어요.\n빛은 옆에서 들어오게 두세요.",
             "max_chars": 80},
        ],
    ),
    (
        "point", "bg_05.png",
        [
            {"id": "s05_badge", "role": "badge", "text": "03"},
            {"id": "s05_headline", "role": "headline", "text": "책상 위 물건은\n손이 닿는 것만", "max_chars": 24},
            {"id": "s05_body", "role": "body",
             "text": "하루에 한 번도 만지지 않은 물건은 서랍으로 내려보내세요.",
             "max_chars": 80},
        ],
    ),
    (
        "point", "bg_06.png",
        [
            {"id": "s06_badge", "role": "badge", "text": "04"},
            {"id": "s06_headline", "role": "headline", "text": "케이블은\n보이지 않게", "max_chars": 24},
            {"id": "s06_body", "role": "body",
             "text": "시야에 들어오는 선이 줄면 책상이 실제보다 넓어 보여요.",
             "max_chars": 80},
        ],
    ),
    (
        "proof", "bg_07.png",
        [
            {"id": "s07_badge", "role": "badge", "text": "확인"},
            {"id": "s07_headline", "role": "headline", "text": "바꾸기 전후를\n한 장씩 찍어두세요", "max_chars": 24},
            {"id": "s07_body", "role": "body",
             "text": "사진으로 비교하면 다시 어질러졌을 때 되돌릴 기준이 생겨요.",
             "max_chars": 80},
            {"id": "s07_caption_note", "role": "caption_note",
             "text": "※ 이 세트의 문장은 M1 검증용 더미다. 출처가 필요한 수치는 넣지 않았다."},
        ],
    ),
    (
        "summary", "bg_08.png",
        [
            {"id": "s08_headline", "role": "headline", "text": "저장해두고\n하나씩 지우세요", "max_chars": 24},
            {"id": "s08_bullet_1", "role": "bullet", "text": "· 모니터 높이 올리기"},
            {"id": "s08_bullet_2", "role": "bullet", "text": "· 조명 옆으로 옮기기"},
            {"id": "s08_bullet_3", "role": "bullet", "text": "· 안 쓰는 물건 내려보내기"},
            {"id": "s08_bullet_4", "role": "bullet", "text": "· 케이블 시야에서 치우기"},
            {"id": "s08_bullet_5", "role": "bullet", "text": "· 전후 사진 찍어두기"},
        ],
    ),
    (
        "cta", "bg_09.png",
        [
            {"id": "s09_eyebrow", "role": "eyebrow", "text": "SAVE THIS"},
            {"id": "s09_headline", "role": "headline", "text": "오늘 하나만\n골라서 해보세요", "max_chars": 24},
            {"id": "s09_body", "role": "body", "text": "아홉 개를 한 번에 하려다 아무것도 못 바꾸는 게 제일 흔한 실패예요.", "max_chars": 80},
            {"id": "s09_cta", "role": "cta", "text": "저장 →", "max_chars": 12},
        ],
    ),
]


def demo_style_dna() -> dict:
    return json.loads(DEMO_DNA_PATH.read_text(encoding="utf-8"))


def demo_render_set(platform: str = "instagram", language: str = "ko") -> RenderSet:
    dna = demo_style_dna()
    spec = platform_spec(platform)
    theme = Theme.from_dna(dna, spec, spec.canvas)

    slides = []
    for i, (role, background, blocks) in enumerate(_SLIDES, start=1):
        slides.append(
            RenderSlide(
                index=i,
                role=role,
                background=background,
                blocks=[
                    RenderBlock(
                        id=b["id"],
                        role=b["role"],
                        text=b["text"],
                        max_chars=b.get("max_chars"),
                        emphasis_spans=list(b.get("emphasis_spans", [])),
                    )
                    for b in blocks
                ],
            )
        )

    return RenderSet(
        set_id="demo0001",
        account="deskreset",
        platform=platform,
        language=language,
        theme=theme,
        slides=slides,
    )


def demo_copy(platform: str = "instagram") -> dict:
    """A5 CopySmith가 냈을 법한 모양의 카피 묶음.

    A10 Localizer의 입력은 렌더 세트가 아니라 이 dict다 — 현지화는 좌표가 아니라
    문장을 다루는 일이고, 좌표는 도착 캔버스에서 다시 실측된다.
    """
    render_set = demo_render_set(platform=platform)
    slides = []
    for slide in render_set.slides:
        slides.append(
            {
                "index": slide.index,
                "role": slide.role,
                "layout_template": slide.template(),
                "copy_blocks": [
                    {
                        "id": block.id,
                        "role": block.role,
                        "text": block.text,
                        "max_chars": block.max_chars,
                        "emphasis_spans": [list(s) for s in block.emphasis_spans],
                        "editable": True,
                    }
                    for block in slide.blocks
                ],
            }
        )
    return {
        "slides": slides,
        "caption": dict(CAPTION),
        "hashtags": list(HASHTAGS),
        "template_swaps": {},
        "warnings": [],
        "attempts": 1,
    }
