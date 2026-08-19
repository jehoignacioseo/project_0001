"""A5 CopySmith — StyleDNA의 copy 블록을 하드 제약으로 삼아 카피를 쓴다.

절대 규칙 #8: 팔레트·타이포·**글자수는 하드 제약**이다.

제약을 프롬프트에 싣는 것과, 결과가 제약을 지켰는지 확인하는 것은 별개다.
여기서는 모델에게 제약을 알려주고, 나온 결과를 `core.agents.constraints`로 직접
세어 본 뒤, 넘치면 축약을 요청한다.

  초과 → 축약 요청 (최대 3회)
       → 그래도 넘치면 레이아웃 템플릿을 더 큰 텍스트존으로 교체하고 마지막 1회
       → 그래도 넘치면 **명시적으로 실패**한다 (절대 규칙 #6)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from apps.api.models import PipelineStage
from apps.api.schemas.generated.copy import Caption
from core.agents.base import Agent, AgentContext
from core.agents.constraints import (
    CaptionConstraints,
    CopyConstraints,
    Violation,
    blocking,
    describe,
)
from core.config import platform_spec
from core.providers.llm import LLMClient, default_client

#: 템플릿별로 쓸 수 있는 블록 역할. 템플릿에 없는 슬롯을 채워 봐야 렌더에서 사라진다.
TEMPLATE_ROLES: dict[str, tuple[str, ...]] = {
    "hook": ("eyebrow", "headline", "subhead"),
    "point": ("badge", "eyebrow", "headline", "body", "bullet", "caption_note"),
    "cta": ("eyebrow", "headline", "body", "cta"),
}

#: 축약으로도 안 될 때 옮겨 갈, 텍스트존이 더 큰 템플릿.
#: point는 헤드라인 + 본문 + 불릿까지 받아 M1 세 템플릿 중 가장 여유가 크다.
ROOMIER_TEMPLATE: dict[str, str] = {"hook": "point", "cta": "point"}

MAX_SHRINK_ATTEMPTS = 3


class CopyError(RuntimeError):
    """카피가 제약을 지키지 못했고 재시도가 소진됐다. 조용히 통과시키지 않는다."""


class CopyBlockDraft(BaseModel):
    role: str = Field(description="eyebrow | headline | subhead | body | bullet | badge | cta | caption_note")
    text: str
    emphasis_spans: list[list[int]] = Field(
        default_factory=list,
        description="강조할 [시작, 끝) 문자 인덱스. 헤드라인에서 한 구간만, 없으면 비운다.",
    )


class SlideCopyDraft(BaseModel):
    index: int
    blocks: list[CopyBlockDraft]


class SlideCopySet(BaseModel):
    slides: list[SlideCopyDraft]


class CaptionDraft(BaseModel):
    caption: Caption
    hashtags: list[str]


@dataclass
class CopyResult:
    slides: list[dict[str, Any]]
    caption: dict[str, Any]
    hashtags: list[str]
    #: 축약으로 해결되지 않아 템플릿을 바꾼 슬라이드 {index: 새 템플릿}
    template_swaps: dict[int, str] = field(default_factory=dict)
    #: 통과는 시켰지만 사용자에게 보고할 항목
    warnings: list[Violation] = field(default_factory=list)
    attempts: int = 1


def _constraint_brief(c: CopyConstraints) -> str:
    lines = [
        f"- 언어: {c.language} · 어미/말투: {c.register}",
        f"- 헤드라인 상한: {c.headline_char_limit}자 (줄바꿈은 세지 않는다)",
        f"- 본문 상한: {c.body_char_limit}자",
        f"- 문장부호 습관: {c.punctuation_habits}",
    ]
    if c.emoji_density == 0:
        lines.append("- **이모지를 쓰지 않는다.** 하나도 넣지 마라.")
    else:
        lines.append(
            f"- 이모지 밀도 {c.emoji_density} (글자수 대비). "
            f"쓸 수 있는 이모지는 {''.join(c.emoji_palette)}뿐이다."
        )
    if c.forbidden_words:
        lines.append(f"- **금지어(절대 쓰지 마라)**: {', '.join(c.forbidden_words)}")
    if c.signature_phrases:
        lines.append(f"- 이 계정이 반복해 쓰는 구문: {', '.join(c.signature_phrases)}")
    if c.cover_title_limit:
        lines.append(f"- 커버 제목은 {c.cover_title_limit}자를 넘으면 피드에서 잘린다")
    return "\n".join(lines)


_SYSTEM = """너는 특정 계정의 목소리로 캐러셀 카피를 쓰는 카피라이터다.

가장 중요한 것은 **글자수 상한을 지키는 것**이다. 상한을 넘긴 카피는 아무리 좋아도
버려진다. 문장을 먼저 쓰고 줄이지 말고, 처음부터 상한 안에서 써라.

- 헤드라인은 한 호흡에 읽히게. 필요하면 \\n으로 두 줄까지 나눈다(줄바꿈은 글자수에 안 센다).
- emphasis_spans는 헤드라인에서 **의미의 핵**이 되는 한 구간만 잡는다. 없으면 비워라.
  인덱스는 text의 문자 위치이며 [시작, 끝)이다. 줄바꿈(\\n)도 한 글자로 센다.
- 주어진 계정의 말투를 흉내 내라. 일반적인 마케팅 문구를 쓰지 마라.
- 근거 없는 숫자·통계·연도를 만들어 내지 마라. 확인되지 않은 것은 단정하지 않는다.
"""


class CopySmith(Agent):
    name = "A5 CopySmith"
    stage = PipelineStage.COPY
    milestone = "M2"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("drafting")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        result = self.write(state["outline"], ctx)
        return {
            **state,
            "copy": {
                "slides": result.slides,
                "caption": result.caption,
                "hashtags": result.hashtags,
                "template_swaps": result.template_swaps,
                "warnings": [str(w) for w in result.warnings],
                "attempts": result.attempts,
            },
        }

    # ── 카피 ────────────────────────────────────────────────────────────
    def write(self, outline: dict[str, Any], ctx: AgentContext) -> CopyResult:
        dna = ctx.style_dna
        if dna is None:
            raise CopyError("StyleDNA 없이는 카피를 쓸 수 없다 — copy 블록이 하드 제약이다")
        spec = platform_spec(ctx.platform)
        constraints = CopyConstraints.from_dna(dna, spec)

        templates = {s["index"]: s["layout_template"] for s in outline["slides"]}
        draft = self._draft_slides(outline, ctx, constraints, templates)
        slides, swaps, attempts = self._enforce(draft, outline, ctx, constraints, templates)
        caption, hashtags, warnings = self._write_caption(outline, ctx, dna, spec)

        return CopyResult(
            slides=slides,
            caption=caption,
            hashtags=hashtags,
            template_swaps=swaps,
            warnings=warnings,
            attempts=attempts,
        )

    def _draft_slides(
        self,
        outline: dict[str, Any],
        ctx: AgentContext,
        constraints: CopyConstraints,
        templates: dict[int, str],
    ) -> SlideCopySet:
        dna = ctx.style_dna
        hook = outline["hook_candidates"][outline["chosen_hook_index"]]
        slide_lines = []
        for slide in outline["slides"]:
            allowed = TEMPLATE_ROLES[templates[slide["index"]]]
            slide_lines.append(
                f"{slide['index']}. [{slide['role']}] 메시지: {slide['single_message']}\n"
                f"   쓸 수 있는 블록: {', '.join(allowed)}"
            )

        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"계정: {dna['identity']['one_line']}\n"
                f"독자: {dna['identity']['target_reader']}\n"
                f"플랫폼 문화: {platform_spec(ctx.platform).culture_prompt}\n\n"
                f"제약 (전부 지켜야 한다):\n{_constraint_brief(constraints)}\n\n"
                f"선택된 커버 훅: {hook['text']}\n"
                f"(이 훅을 1번 슬라이드 headline의 출발점으로 삼되, 상한에 맞게 다듬어라)\n\n"
                f"슬라이드:\n" + "\n".join(slide_lines) + "\n\n"
                "슬라이드마다 필요한 블록만 채워라. 모든 슬롯을 억지로 채우지 마라."
            ),
            output_model=SlideCopySet,
            profile="drafting",
        )
        return result.parsed

    def _enforce(
        self,
        draft: SlideCopySet,
        outline: dict[str, Any],
        ctx: AgentContext,
        constraints: CopyConstraints,
        templates: dict[int, str],
    ) -> tuple[list[dict[str, Any]], dict[int, str], int]:
        """제약을 세어 보고, 넘치면 축약을 요청한다."""
        slides = {s.index: s for s in draft.slides}
        swaps: dict[int, str] = {}
        attempt = 1

        while True:
            failures = self._violations(slides, constraints, templates)
            if not failures:
                break

            if attempt <= MAX_SHRINK_ATTEMPTS:
                slides = self._shrink(slides, failures, constraints, templates, attempt)
                attempt += 1
                continue

            # 축약 3회로 안 됐다. 텍스트존이 더 큰 템플릿으로 옮기고 한 번 더.
            escalated = False
            for index in sorted({i for i, _ in failures}):
                current = templates[index]
                roomier = ROOMIER_TEMPLATE.get(current)
                if roomier and roomier != current:
                    templates[index] = roomier
                    swaps[index] = roomier
                    escalated = True
            if not escalated:
                raise CopyError(
                    f"카피가 {MAX_SHRINK_ATTEMPTS}회 축약 후에도 제약을 넘는데 "
                    "옮겨 갈 더 큰 템플릿이 없다. 재생성이 필요하다:\n"
                    + describe([v for _, v in failures])
                )
            slides = self._shrink(slides, failures, constraints, templates, attempt)
            attempt += 1

            remaining = self._violations(slides, constraints, templates)
            if remaining:
                raise CopyError(
                    "템플릿을 바꾸고도 카피가 제약을 넘는다. 조용히 통과시키지 않는다:\n"
                    + describe([v for _, v in remaining])
                )
            break

        out = []
        for slide in outline["slides"]:
            index = slide["index"]
            drafted = slides[index]
            out.append(
                {
                    "index": index,
                    "role": slide["role"],
                    "layout_template": templates[index],
                    "copy_blocks": [
                        {
                            "id": f"s{index:02d}_{b.role}",
                            "role": b.role,
                            "text": b.text,
                            "max_chars": constraints.limit_for(b.role),
                            "emphasis_spans": [list(s) for s in b.emphasis_spans],
                            "editable": True,
                        }
                        for b in drafted.blocks
                    ],
                }
            )
        return out, swaps, attempt

    def _violations(
        self,
        slides: dict[int, SlideCopyDraft],
        constraints: CopyConstraints,
        templates: dict[int, str],
    ) -> list[tuple[int, Violation]]:
        out: list[tuple[int, Violation]] = []
        for index, slide in slides.items():
            allowed = TEMPLATE_ROLES[templates[index]]
            seen: set[str] = set()
            for block in slide.blocks:
                field_name = f"s{index:02d}_{block.role}"
                if block.role not in allowed:
                    out.append(
                        (index, Violation(field_name, f"{templates[index]} 템플릿에 없는 블록이다"))
                    )
                    continue
                if block.role in seen and block.role != "bullet":
                    out.append((index, Violation(field_name, "같은 역할의 블록이 중복됐다")))
                seen.add(block.role)
                for v in blocking(
                    constraints.check_text(block.text, field_name=field_name, role=block.role)
                ):
                    out.append((index, v))
                for start, end in block.emphasis_spans:
                    if not 0 <= start < end <= len(block.text):
                        out.append(
                            (index, Violation(field_name, f"강조 구간 [{start}, {end})이 텍스트를 벗어난다"))
                        )
        return out

    def _shrink(
        self,
        slides: dict[int, SlideCopyDraft],
        failures: list[tuple[int, Violation]],
        constraints: CopyConstraints,
        templates: dict[int, str],
        attempt: int,
    ) -> dict[int, SlideCopyDraft]:
        """문제가 있는 슬라이드만 다시 쓴다. 멀쩡한 슬라이드는 건드리지 않는다."""
        broken = sorted({index for index, _ in failures})
        current = [slides[i] for i in broken]
        detail = "\n".join(f"슬라이드 {i}: {v}" for i, v in failures)

        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"아래 카피가 제약을 어겼다 ({attempt}번째 수정 요청).\n\n"
                f"위반 내역:\n{detail}\n\n"
                f"제약:\n{_constraint_brief(constraints)}\n\n"
                f"현재 카피:\n"
                + "\n".join(
                    f"슬라이드 {s.index} ({templates[s.index]}): "
                    + " / ".join(f"[{b.role}] {b.text}" for b in s.blocks)
                    for s in current
                )
                + "\n\n"
                "**축약해라.** 의미의 핵은 남기고 수식을 덜어내라. 상한을 넘으면 또 버려진다.\n"
                "지적된 슬라이드만 다시 써라. 블록 구성은 유지한다."
            ),
            output_model=SlideCopySet,
            profile="drafting",
        )
        updated = dict(slides)
        for slide in result.parsed.slides:
            if slide.index in updated:
                updated[slide.index] = slide
        return updated

    # ── 캡션 ────────────────────────────────────────────────────────────
    def _write_caption(
        self,
        outline: dict[str, Any],
        ctx: AgentContext,
        dna: dict[str, Any],
        spec: Any,
    ) -> tuple[dict[str, Any], list[str], list[Violation]]:
        rules = CaptionConstraints.from_dna(dna, spec)
        strategy = dna["caption"]["hashtag_strategy"]
        hook = outline["hook_candidates"][outline["chosen_hook_index"]]

        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"계정: {dna['identity']['one_line']}\n"
                f"주제: {outline['title_working']}\n"
                f"커버 훅: {hook['text']}\n"
                f"슬라이드 메시지: {[s['single_message'] for s in outline['slides']]}\n\n"
                f"본문 캡션을 써라.\n"
                f"- 첫 줄(hook_line)은 {rules.fold_at}자 안에서 끝난다. 여기서 잘리면 훅이 사라진다.\n"
                f"- 첫 줄 공식: {dna['caption']['first_line_rule']}\n"
                f"- 전체 길이는 {rules.length_min}~{rules.length_max}자.\n"
                f"- 해시태그는 정확히 {strategy['count']}개. "
                f"구성: 넓은 태그 {strategy['mix']['broad']}, 니치 {strategy['mix']['niche']}, "
                f"브랜드 {strategy['mix']['branded']}, 커뮤니티 {strategy['mix']['community']}.\n"
                f"- 태그는 '#'로 시작하고 중복이 없어야 한다.\n"
                f"- 말투: {dna['copy']['register']}"
            ),
            output_model=CaptionDraft,
            profile="drafting",
        )
        draft = result.parsed
        hashtags = [t if t.startswith("#") else f"#{t}" for t in draft.hashtags]
        violations = rules.check(
            draft.caption.hook_line, draft.caption.body, draft.caption.cta, hashtags
        )
        hard = blocking(violations)
        if hard:
            raise CopyError("캡션이 제약을 어겼다:\n" + describe(hard))
        return draft.caption.model_dump(), hashtags, [v for v in violations if v.severity == "warning"]
