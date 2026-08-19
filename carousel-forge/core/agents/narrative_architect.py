"""A4 NarrativeArchitect — 캐러셀 구조 설계.

StyleDNA의 `narrative_pattern`·`slide_roles_sequence`를 골격으로, 주제의
`supporting_points` 개수에 맞춰 슬라이드 수를 정한다.

두 가지를 특히 지킨다:
  - **커버(1번)에 전체 리소스의 40%를 쓴다.** 훅 후보를 3개 만들어 가장 강한 것을 고른다.
  - **마지막 직전에 저장 유발 요약본을 둔다.** 저장률이 알고리즘의 핵심 지표다.

모델이 고른 구조가 StyleDNA·플랫폼 규격을 벗어나면 코드가 바로잡는다. 구조는
지켜졌는지 세면 되는 것이므로 판정을 다시 모델에게 맡기지 않는다.
"""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from apps.api.schemas.generated.outline import (
    CarouselOutline,
    CtaType,
    HookType,
    NarrativePattern,
    OutlineSlide,
    Role,
)
from core.agents.base import Agent, AgentContext
from core.agents.constraints import Violation
from core.config import PlatformSpec, platform_spec
from core.providers.llm import LLMClient, default_client
from core.render.model import ROLE_TO_TEMPLATE

_SYSTEM = """너는 캐러셀의 서사 구조를 짜는 편집자다.

원칙:
- **커버 한 장이 전부다.** 훅 후보 3개를 서로 다른 공식으로 만들고, 가장 스크롤을
  멈출 것 같은 하나를 고른 뒤 그 이유를 rationale에 적어라. 세 개가 비슷하면 실패다.
- 슬라이드마다 메시지는 **딱 하나**다. 두 개를 담고 싶으면 슬라이드를 나눠라.
- single_message는 카피가 아니라 의도다. 문장을 예쁘게 다듬지 마라 — 그건 다음 단계가 한다.
- visual_brief는 **글자가 없는 배경**을 설명한다. 이미지 안에 텍스트·숫자·로고를
  넣으라는 요구를 절대 쓰지 마라. 글자는 전부 별도 레이어에서 얹힌다.
- 마지막 직전에는 저장을 유발하는 요약(summary)을 둔다. 마지막은 cta다.
"""


class OutlineError(ValueError):
    """구조가 StyleDNA나 플랫폼 규격을 벗어났고 바로잡을 수 없다."""


def resolve_slide_count(dna: dict[str, Any], topic: dict[str, Any], spec: PlatformSpec) -> int:
    """슬라이드 수를 정한다.

    StyleDNA의 범위를 기준으로 삼되, supporting_points를 다 담을 만큼은 확보한다.
    커버 + 포인트들 + 요약 + CTA가 최소 구성이다.
    """
    lo, hi = dna["structure"]["slide_count_range"]
    mode = int(dna["structure"]["slide_count_mode"])
    points = len(topic.get("supporting_points") or [])

    # 커버 1 + 맥락 1 + 포인트 n + 요약 1 + CTA 1
    needed = points + 4
    count = min(max(needed, lo), hi)
    if points == 0:
        count = mode
    return max(spec.min_slides, min(count, spec.max_slides))


def _role_sequence(dna: dict[str, Any], count: int) -> list[str]:
    """StyleDNA의 role 순서를 원하는 길이에 맞춘다.

    늘릴 때는 중간의 point를 반복하고, 줄일 때는 point부터 덜어낸다. 커버·요약·
    CTA는 구조의 뼈대이므로 건드리지 않는다.
    """
    base = list(dna["structure"]["slide_roles_sequence"])
    if not base:
        base = ["hook", "context", "point", "summary", "cta"]

    head = [base[0]] if base[0] == "hook" else ["hook"]
    tail: list[str] = []
    if "cta" in base:
        tail.append("cta")
    middle = [r for r in base[len(head) : len(base) - len(tail)] if r not in ("hook", "cta")]
    if not middle:
        middle = ["point"]

    # 마지막 직전은 저장 유발 요약본 자리다.
    middle = [r for r in middle if r != "summary"]
    body_len = count - len(head) - len(tail) - 1        # -1은 summary
    if body_len < 1:
        # 너무 짧으면 요약을 뺀다 — 뼈대(커버·CTA)를 먼저 지킨다.
        body_len = max(1, count - len(head) - len(tail))
        body = _fit(middle, body_len)
        return head + body + tail
    return head + _fit(middle, body_len) + ["summary"] + tail


def _fit(roles: list[str], length: int) -> list[str]:
    if length <= 0:
        return []
    if len(roles) >= length:
        # 줄일 때는 point를 먼저 덜어낸다.
        trimmed = list(roles)
        while len(trimmed) > length:
            if "point" in trimmed:
                trimmed.remove("point")
            else:
                trimmed.pop()
        return trimmed
    out = list(roles)
    while len(out) < length:
        out.insert(max(1, len(out) - 1), "point")
    return out


class NarrativeArchitect(Agent):
    name = "A4 NarrativeArchitect"
    stage = PipelineStage.ARCHITECT
    milestone = "M2"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("reasoning")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        dna = ctx.style_dna
        if dna is None:
            raise OutlineError("StyleDNA 없이는 구조를 짤 수 없다 (A4는 DNA의 골격을 쓴다)")
        topic = state["topic"]
        spec = platform_spec(ctx.platform)

        count = resolve_slide_count(dna, topic, spec)
        roles = _role_sequence(dna, count)
        structure = dna["structure"]

        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"플랫폼: {spec.display_name} · 언어: {ctx.language}\n"
                f"플랫폼 문화: {spec.culture_prompt}\n\n"
                f"계정 스타일:\n"
                f"- 서사 패턴: {structure['narrative_pattern']}\n"
                f"- 훅 공식: {structure['hook_type']}\n"
                f"- CTA 유형: {structure['cta_type']}\n"
                f"- 커버 규칙: {structure['cover_rule']}\n"
                f"- 계정 한 줄: {dna['identity']['one_line']}\n"
                f"- 독자: {dna['identity']['target_reader']}\n\n"
                f"주제:\n"
                f"- 제목안: {topic['title_working']}\n"
                f"- 각도: {topic['angle']}\n"
                f"- 핵심 메시지: {topic['key_message']}\n"
                f"- 독자: {topic['audience']}\n"
                f"- 근거 포인트: {topic['supporting_points']}\n"
                f"- CTA 의도: {topic['cta_intent']}\n"
                f"- 반드시 포함: {topic['constraints']['must_include']}\n"
                f"- 반드시 회피: {topic['constraints']['must_avoid']}\n\n"
                f"슬라이드는 정확히 {count}장이고, role 순서는 다음으로 고정한다:\n"
                f"{roles}\n\n"
                "이 순서를 그대로 지켜 각 슬라이드의 single_message와 visual_brief를 채워라."
            ),
            output_model=CarouselOutline,
            profile="reasoning",
        )
        outline = self._repair(result.parsed, roles=roles, count=count, dna=dna)
        return {**state, "outline": outline.model_dump()}

    def _repair(
        self, outline: CarouselOutline, *, roles: list[str], count: int, dna: dict[str, Any]
    ) -> CarouselOutline:
        """모델이 어긋나게 답했으면 코드가 바로잡는다.

        구조는 '지켜졌는지 세면 되는 것'이라 다시 물어볼 이유가 없다. 다만 내용을
        지어내지는 않는다 — 슬라이드 수가 모자라면 실패로 보고한다.
        """
        slides = list(outline.slides)
        if len(slides) != count:
            if len(slides) > count:
                slides = slides[:count]
            else:
                raise OutlineError(
                    f"슬라이드가 {len(slides)}장 나왔는데 {count}장이 필요하다. "
                    "모자란 장을 임의로 채우지 않는다 — 재생성이 필요하다."
                )

        repaired: list[OutlineSlide] = []
        for i, (slide, role) in enumerate(zip(slides, roles, strict=True), start=1):
            repaired.append(
                slide.model_copy(
                    update={
                        "index": i,
                        "role": Role(role),
                        # 레이아웃 템플릿은 우리 쪽 자산이다. 모델이 지어낸 이름
                        # (예: "cover-title-sub")을 받아들이면 렌더가 깨진다.
                        "layout_template": ROLE_TO_TEMPLATE[role],
                    }
                )
            )

        chosen = outline.chosen_hook_index
        if not 0 <= chosen < len(outline.hook_candidates):
            # 범위를 벗어나면 점수가 가장 높은 후보로 되돌린다.
            chosen = max(
                range(len(outline.hook_candidates)),
                key=lambda i: outline.hook_candidates[i].strength_score,
            )

        return outline.model_copy(
            update={
                "slides": repaired,
                "slide_count": count,
                "chosen_hook_index": chosen,
                # StyleDNA가 정한 값으로 되돌린다. 이 셋은 계정의 골격이지
                # 매번 새로 고를 대상이 아니다.
                "narrative_pattern": NarrativePattern(dna["structure"]["narrative_pattern"]),
                "cta_type": CtaType(dna["structure"]["cta_type"]),
                "hook_type": HookType(dna["structure"]["hook_type"]),
            }
        )


def check_outline(outline: dict[str, Any], spec: PlatformSpec) -> list[Violation]:
    """구조가 규격을 지켰는지 센다. A9 QualityGate가 그대로 쓴다."""
    out: list[Violation] = []
    slides = outline["slides"]
    count = len(slides)

    if not spec.min_slides <= count <= spec.max_slides:
        out.append(
            Violation("outline", f"{count}장은 {spec.key}의 허용 범위 "
                                 f"{spec.min_slides}~{spec.max_slides}장 밖이다")
        )
    if [s["index"] for s in slides] != list(range(1, count + 1)):
        out.append(Violation("outline", "슬라이드 index가 1..N 연속이 아니다"))
    if slides and slides[0]["role"] != "hook":
        out.append(Violation("outline", "첫 장이 hook이 아니다 — 커버가 훅을 맡아야 한다"))
    if slides and slides[-1]["role"] != "cta":
        out.append(Violation("outline", "마지막 장이 cta가 아니다", severity="warning"))
    if count >= 5 and not any(s["role"] == "summary" for s in slides):
        out.append(
            Violation(
                "outline",
                "저장 유발 요약(summary) 슬라이드가 없다 — 저장률이 핵심 지표다",
                severity="warning",
            )
        )
    if len(outline["hook_candidates"]) != 3:
        out.append(Violation("outline.hook_candidates", "훅 후보는 3개여야 한다"))

    for slide in slides:
        brief = slide["visual_brief"].lower()
        for marker in ("text saying", "with the words", "글자", "텍스트를 넣", "문구를 넣"):
            if marker in brief:
                out.append(
                    Violation(
                        f"slides[{slide['index']}].visual_brief",
                        f"배경에 글자를 넣으라는 요구가 있다 ({marker!r}) — "
                        "글자는 렌더 레이어에서만 처리한다",
                    )
                )
    return out
