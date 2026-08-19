"""A7 ArtDirector — 텍스트가 없는 배경만 생성한다.

절대 규칙 #5: **AI 생성 텍스트를 이미지 프롬프트에 넣지 않는다.** 글자는 항상
렌더 레이어에서 처리한다. AI가 이미지 안에 그린 글자는 거의 언제나 뭉개지고,
무엇보다 그 순간 Figma에서 편집할 수 없게 된다.

프롬프트는 6블록 구조를 따른다:
    [배경/상황] → [주체] → [핵심 디테일] → [조명/렌즈] → [스타일 제약] → [네거티브]

슬라이드 간 **시각 일관성 잠금**이 이 에이전트의 핵심이다. 한 세트의 배경들이
따로 놀면 캐러셀이 아니라 이미지 묶음이 된다. 팔레트·조명·렌즈감·그레인을 한 번
정해 모든 슬라이드에 같은 문자열로 붙이고, 슬라이드마다 바뀌는 것은 앞쪽 두
블록(상황·주체)뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext
from core.config import model_routing, platform_spec
from core.providers.image import ImageProvider, ImageRequest, TextInPromptError
from core.providers.llm import LLMClient, default_client
from core.render.model import Theme

#: 텍스트가 얹힐 자리를 비워 두라는 지시. StyleDNA의 text_zone에서 나온다.
LOW_DETAIL_ZONE: dict[str, str] = {
    "top": "keep the upper third quiet and low in detail — flat tone, no focal subject there",
    "center": "keep the middle band quiet and low in detail — the subject sits high or low, not centred",
    "bottom": "keep the lower half quiet and low in detail — flat tone, no focal subject there",
    "split": "keep the top and bottom bands quiet — detail belongs in the middle only",
    "full-bleed": "keep overall detail low and evenly distributed — no single busy focal area",
}

#: 색을 말로 옮길 때 쓰는 단서. 팔레트 hex를 그대로 프롬프트에 넣어도 모델이
#: 정확히 재현하지는 못하지만, 색 이름과 함께 주면 방향은 잡힌다.
TREATMENT_PHRASES: dict[str, str] = {
    "film-grain": "visible 35mm film grain",
    "desaturated": "muted, desaturated colour",
    "high-contrast": "strong contrast between light and shadow",
    "warm-shift": "warm colour cast",
    "duotone": "duotone treatment",
}


class ArtDirectionError(RuntimeError):
    pass


class SlideVisual(BaseModel):
    """슬라이드 한 장의 배경 지시. 앞쪽 두 블록만 슬라이드마다 달라진다."""

    index: int
    scene: str = Field(description="배경/상황. 장소와 분위기. 글자·간판·문서는 넣지 마라.")
    subject: str = Field(description="주체. 사물이나 손 정도. 없으면 'no subject, empty scene'")
    detail: str = Field(description="핵심 디테일 한두 가지. 질감·소품.")


class VisualPlan(BaseModel):
    """세트 전체의 시각 계획. 뒤쪽 블록은 한 번만 정해 모든 장에 공유된다."""

    lighting: str = Field(description="조명과 렌즈감. 세트 전체에 공통으로 적용된다.")
    palette_words: str = Field(description="팔레트를 말로 옮긴 것 (예: 'deep charcoal and warm cream')")
    slides: list[SlideVisual]


@dataclass
class BackgroundPrompt:
    """완성된 배경 프롬프트 한 건."""

    slide_index: int
    prompt: str
    negative: list[str]
    seed: int | None = None
    blocks: dict[str, str] = field(default_factory=dict)

    def as_log(self) -> str:
        return f"슬라이드 {self.slide_index}: {self.prompt[:120]}…"


_SYSTEM = """너는 캐러셀 배경 이미지의 아트 디렉터다.

**배경에는 글자가 없다.** 간판, 문서, 화면, 책 표지, 라벨처럼 글자가 딸려 오는
소재는 아예 쓰지 마라. 글자는 전부 나중에 별도 레이어로 얹힌다.

- 한 세트의 배경은 같은 날 같은 카메라로 찍은 것처럼 보여야 한다. lighting은
  한 번만 정해 모든 장에 공통으로 쓰인다. 장마다 다른 시간대·다른 렌즈를 쓰지 마라.
- scene과 subject는 슬라이드의 메시지를 **설명하지 말고 분위기로 받쳐라.**
  메시지를 그림으로 옮기려 들면 유치해진다.
- subject가 필요 없으면 'no subject, empty scene'이라고 적어라. 빈 배경이
  어설픈 소품보다 낫다.
- 영어로 써라. 이미지 모델이 영어에서 가장 안정적이다.
"""


def build_prompt(
    visual: SlideVisual,
    plan: VisualPlan,
    theme: Theme,
    dna: dict[str, Any],
    *,
    canvas_ratio: str,
) -> BackgroundPrompt:
    """6블록 구조로 프롬프트를 조립한다. 순수 함수 — 모델을 부르지 않는다."""
    imagery = dna["visual"]["imagery"]
    treatments = [TREATMENT_PHRASES[t] for t in imagery["treatment"] if t in TREATMENT_PHRASES]

    zone_rule = LOW_DETAIL_ZONE.get(theme.text_zone, LOW_DETAIL_ZONE["full-bleed"])
    style_bits = [
        f"colour palette: {plan.palette_words}",
        *treatments,
        f"{canvas_ratio} vertical framing",
        zone_rule,
        "photographic, natural imperfection, no digital gloss",
    ]
    if imagery["grain_intensity"] > 0.25:
        style_bits.append("noticeable grain, not clean digital")

    blocks = {
        "scene": visual.scene.strip().rstrip("."),
        "subject": visual.subject.strip().rstrip("."),
        "detail": visual.detail.strip().rstrip("."),
        "lighting": plan.lighting.strip().rstrip("."),
        "style": ", ".join(style_bits),
    }
    prompt = ". ".join(
        blocks[key] for key in ("scene", "subject", "detail", "lighting", "style")
    ) + "."

    request = ImageRequest(prompt=prompt, width=1, height=1)
    negative = request.full_negative()

    # 조립이 끝난 뒤 한 번 더 본다. 모델이 scene에 "a sign that reads…"를 넣었다면
    # 여기서 걸러야 한다 — 배경에 글자가 들어가는 순간 이 프로그램은 실패한 것이다.
    ImageProvider.assert_no_text_request(prompt)

    return BackgroundPrompt(
        slide_index=visual.index, prompt=prompt, negative=negative, blocks=blocks
    )


class ArtDirector(Agent):
    name = "A7 ArtDirector"
    stage = PipelineStage.VISUAL_GEN
    milestone = "M4"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("reasoning")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        prompts = self.plan(state["outline"], ctx)
        return {**state, "background_prompts": [
            {
                "slide_index": p.slide_index,
                "prompt": p.prompt,
                "negative": p.negative,
                "blocks": p.blocks,
            }
            for p in prompts
        ]}

    def plan_from_briefs(
        self, outline: dict[str, Any], ctx: AgentContext
    ) -> list[BackgroundPrompt]:
        """모델을 부르지 않고 A4의 `visual_brief`만으로 프롬프트를 짠다.

        A4가 이미 슬라이드마다 필요한 비주얼을 적어 두었다. 브리프가 충분하면
        같은 내용을 다시 쓰게 하려고 모델을 한 번 더 부를 이유가 없다.
        조명·팔레트는 DNA에서 결정론적으로 만들어 세트 전체에 공유한다.
        """
        dna = ctx.style_dna
        if dna is None:
            raise ArtDirectionError("StyleDNA 없이는 배경을 지시할 수 없다")
        spec = platform_spec(ctx.platform)
        theme = Theme.from_dna(dna, spec, spec.canvas)
        palette = dna["visual"]["palette"]
        imagery = dna["visual"]["imagery"]

        plan = VisualPlan(
            lighting=(
                "soft directional daylight from one side, 50mm lens, shallow depth of field, "
                "consistent across every frame in the set"
            ),
            palette_words=(
                f"背景 {palette['background'][0]} with {palette['text'][0]} and "
                f"{palette['accent'][0]} accents"
            ).replace("背景", "background"),
            slides=[],
        )

        prompts = []
        for slide in outline["slides"]:
            brief = (slide.get("visual_brief") or "").strip()
            if not brief:
                raise ArtDirectionError(
                    f"슬라이드 {slide['index']}에 visual_brief가 없다. "
                    "브리프 없이 배경을 지어내지 않는다 — plan()으로 모델에 맡겨라."
                )
            visual = SlideVisual(
                index=slide["index"],
                scene=brief,
                subject="no subject, empty scene" if imagery["type_mix"]["photo"] < 0.4 else "a single object, off-centre",
                detail=imagery["subject_rules"],
            )
            prompts.append(
                build_prompt(visual, plan, theme, dna, canvas_ratio=spec.canvas.ratio)
            )
        return prompts

    def plan(self, outline: dict[str, Any], ctx: AgentContext) -> list[BackgroundPrompt]:
        dna = ctx.style_dna
        if dna is None:
            raise ArtDirectionError("StyleDNA 없이는 배경을 지시할 수 없다 — 팔레트가 잠금의 축이다")
        spec = platform_spec(ctx.platform)
        theme = Theme.from_dna(dna, spec, spec.canvas)
        palette = dna["visual"]["palette"]
        imagery = dna["visual"]["imagery"]

        slide_lines = "\n".join(
            f"{s['index']}. [{s['role']}] {s['single_message']}\n"
            f"   비주얼 메모: {s['visual_brief']}"
            for s in outline["slides"]
        )
        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"계정: {dna['identity']['one_line']}\n"
                f"팔레트: 배경 {palette['background'][0]} · 텍스트 {palette['text'][0]} "
                f"· 액센트 {palette['accent'][0]}\n"
                f"이미지 성향: 사진 {imagery['type_mix']['photo']} / "
                f"일러스트 {imagery['type_mix']['illustration']} / "
                f"단색·그라디언트 {imagery['type_mix']['solid_or_gradient']}\n"
                f"후보정: {imagery['treatment']}\n"
                f"피사체 규칙: {imagery['subject_rules']}\n"
                f"텍스트가 얹힐 영역: {theme.text_zone} "
                f"→ {LOW_DETAIL_ZONE.get(theme.text_zone, '')}\n\n"
                f"슬라이드 {len(outline['slides'])}장:\n{slide_lines}\n\n"
                "세트 전체에 공통으로 쓸 조명·렌즈감을 하나 정하고, 슬라이드마다 "
                "장면·주체·디테일을 적어라."
            ),
            output_model=VisualPlan,
            profile="reasoning",
        )
        plan = result.parsed

        by_index = {v.index: v for v in plan.slides}
        prompts = []
        for slide in outline["slides"]:
            visual = by_index.get(slide["index"])
            if visual is None:
                raise ArtDirectionError(
                    f"슬라이드 {slide['index']}의 배경 지시가 없다. 임의로 채우지 않는다."
                )
            try:
                prompts.append(
                    build_prompt(visual, plan, theme, dna, canvas_ratio=spec.canvas.ratio)
                )
            except TextInPromptError as exc:
                raise ArtDirectionError(
                    f"슬라이드 {slide['index']} 배경 프롬프트에 글자 요구가 섞였다: {exc}"
                ) from exc
        return prompts


def provider_chain() -> list[str]:
    """`config/models.yaml`의 폴백 순서."""
    return list(model_routing()["image"]["chain"])
