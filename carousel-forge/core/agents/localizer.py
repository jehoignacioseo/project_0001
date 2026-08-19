"""A10 Localizer — 번역이 아니라 현지화다.

한국어 인스타그램 세트를 중국어 샤오홍슈 세트로 바꾸는 일에는 서로 다른 네 가지가
섞여 있다. 하나로 뭉뚱그리면 셋을 놓친다.

  1. **언어** — 직역 금지. 같은 메시지를 그 언어 독자가 스스로 쓰듯 다시 쓴다.
  2. **조판** — 중국어는 같은 의미를 15~30% 짧게 쓰지만 한자는 한글보다 넓다.
     두 힘이 반대로 작용하므로 어림하지 않고 `core.render.capacity`로 실측한다.
  3. **캔버스** — 4:5 → 3:4. 레이아웃은 `Theme.from_dna(dna, spec, canvas)`가
     새 캔버스 기준으로 다시 계산한다. 좌표를 옮겨 적는 코드는 없다 (절대 규칙 #3).
  4. **해시태그** — 번역 대상이 아니다. 그 언어권에서 실제 쓰이는 태그를 **다시
     조사**한다. 한국어 태그를 직역한 태그는 검색량이 사실상 0이다.

원본과의 연결은 `parent_set_id` + `variant_type='translation'`으로 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from apps.api.models import PipelineStage, VariantType
from apps.api.schemas.generated.copy import Caption
from core.agents.base import Agent, AgentContext
from core.agents.constraints import (
    CaptionConstraints,
    CopyConstraints,
    Violation,
    blocking,
    describe,
    visible_length,
)
from core.config import (
    LocalizationPair,
    language_spec,
    localization_pair,
    platform_spec,
)
from core.platform.base import adapter_for
from core.providers.llm import LLMClient, default_client
from core.render.capacity import RoleCapacity

MAX_SHRINK_ATTEMPTS = 3

#: 언어별 대표 폰트를 StyleDNA 어디서 읽을지. 폰트는 설정이 아니라 계정 자산이므로
#: `config/`가 아니라 StyleDNA의 typography 블록에서 가져온다 (절대 규칙 #8).
DNA_FONT_KEY: dict[str, str] = {
    "ko": "korean_font",
    "zh": "chinese_font",
    "en": "latin_font",
}


class LocalizationError(RuntimeError):
    """현지화가 제약을 지키지 못했거나 필요한 조사를 못 했다. 조용히 넘기지 않는다."""


# ── 구조화 출력 ─────────────────────────────────────────────────────────

class LocalizedBlock(BaseModel):
    id: str = Field(description="원본 블록 id를 그대로 쓴다. 새 id를 만들지 않는다.")
    text: str
    emphasis_spans: list[list[int]] = Field(
        default_factory=list,
        description="강조할 [시작, 끝) 문자 인덱스. 원본 위치가 아니라 새 문장 기준이다.",
    )


class LocalizedSlide(BaseModel):
    index: int
    blocks: list[LocalizedBlock]


class LocalizedCopy(BaseModel):
    slides: list[LocalizedSlide]
    caption: Caption
    # `register`는 pydantic BaseModel의 속성과 이름이 겹친다.
    target_register: str = Field(description="도착 언어에서 이 계정의 말투를 뭐라고 부를지")
    signature_phrases: list[str] = Field(
        default_factory=list,
        description="원본의 반복 구문에 대응하는 도착 언어 표현. 직역이 아니라 대응물.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="직역을 피하려고 의미를 바꾼 곳, 대응물이 없어 풀어 쓴 곳",
    )


class ResearchedTag(BaseModel):
    tag: str = Field(description="'#'로 시작하는 태그")
    kind: str = Field(description="broad | niche | branded | community")
    evidence: str = Field(description="이 태그가 실제로 쓰인다고 판단한 근거")


class HashtagSet(BaseModel):
    tags: list[ResearchedTag]


# ── 결과 ────────────────────────────────────────────────────────────────

@dataclass
class LocalizationResult:
    platform: str
    language: str
    #: 도착 언어/플랫폼에 맞춰 다시 잡은 StyleDNA. 원본을 덮어쓰지 않는다.
    style_dna: dict[str, Any]
    copy: dict[str, Any]
    parent_set_id: str | None = None
    variant_type: VariantType = VariantType.TRANSLATION
    capacity: dict[str, RoleCapacity] = field(default_factory=dict)
    hashtag_research: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    attempts: int = 1

    def summary(self) -> str:
        lines = [
            f"{self.platform} / {self.language} · {len(self.copy['slides'])}장 "
            f"· 해시태그 {len(self.copy['hashtags'])}개 (재조사)",
            f"  원본 연결: parent_set_id={self.parent_set_id} "
            f"variant_type={self.variant_type}",
            f"  글자수 상한: 헤드라인 {self.style_dna['copy']['headline_char_limit']}자 "
            f"· 본문 {self.style_dna['copy']['body_char_limit_per_slide']}자",
        ]
        for cap in self.capacity.values():
            lines.append(f"  실측 수용량 — {cap}")
        for note in self.notes:
            lines.append(f"  메모: {note}")
        for warning in self.warnings:
            lines.append(f"  {warning}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "language": self.language,
            "parent_set_id": self.parent_set_id,
            "variant_type": str(self.variant_type),
            "style_dna": self.style_dna,
            "copy": self.copy,
            "capacity": {
                role: {
                    "chars_per_line": cap.chars_per_line,
                    "max_lines": cap.max_lines,
                    "chars": cap.chars,
                    "line_width_px": cap.line_width_px,
                }
                for role, cap in self.capacity.items()
            },
            "hashtag_research": self.hashtag_research,
            "notes": self.notes,
            "warnings": [str(w) for w in self.warnings],
            "attempts": self.attempts,
        }


# ── StyleDNA 재조준 ─────────────────────────────────────────────────────

def retarget_dna(
    dna: dict[str, Any],
    *,
    target_language: str,
    target_platform: str,
    capacity: dict[str, RoleCapacity] | None = None,
) -> tuple[dict[str, Any], list[Violation]]:
    """StyleDNA를 도착 언어/플랫폼에 맞춰 다시 잡는다.

    바꾸는 것은 **언어에 매인 것들**뿐이다 — 폰트 패밀리, 글자수 상한, 언어 코드.
    팔레트·레이아웃·이미지 스타일은 계정의 정체성이므로 언어가 바뀌어도 그대로 둔다.
    """
    import copy as _copy

    source_language = dna["copy"]["language"]
    pair = localization_pair(source_language, target_language)
    out = _copy.deepcopy(dna)
    warnings: list[Violation] = []

    # ── 폰트 ────────────────────────────────────────────────────────────
    key = DNA_FONT_KEY.get(target_language)
    typography = out["visual"]["typography"]
    family = typography.get(key) if key else None
    if not family:
        raise LocalizationError(
            f"StyleDNA에 {target_language} 폰트가 없다 "
            f"(visual.typography.{key}). 폴백 폰트로 조판하면 실측 좌표와 실제 "
            "글자 모양이 갈라진다."
        )
    for role in ("headline", "body", "accent"):
        typography[role]["family"] = family
        # 폴백에 라틴 폰트를 앞세우지 않는다. 브라우저는 글리프 단위로 폴백하지만
        # Figma는 그렇지 않아서, 플러그인이 만든 TextNode의 한자가 두부가 된다.
        # 편집 가능한 산출물이 목적이므로 도착 언어 폰트가 반드시 첫 번째다.
        typography[role]["fallback"] = ["sans-serif"]

    # ── 글자수 상한 ─────────────────────────────────────────────────────
    out["copy"]["language"] = target_language
    limits, limit_warnings = _retarget_limits(dna["copy"], pair, capacity)
    out["copy"].update(limits)
    warnings += limit_warnings

    # ── 캡션 ────────────────────────────────────────────────────────────
    spec = platform_spec(target_platform)
    caption = out["caption"]
    lo, hi = (int(v * pair.hard_ratio) for v in dna["caption"]["length_range"])
    caption["length_range"] = [lo, min(hi, spec.caption_max_chars)]
    if hi > spec.caption_max_chars:
        warnings.append(
            Violation(
                "caption.length_range",
                f"이 계정의 캡션 상한 {hi}자가 {spec.display_name} 상한 "
                f"{spec.caption_max_chars}자를 넘어 플랫폼 쪽으로 맞췄다",
                severity="warning",
            )
        )
    strategy = caption["hashtag_strategy"]
    if int(strategy["count"]) > spec.hashtag_max:
        warnings.append(
            Violation(
                "caption.hashtag_strategy.count",
                f"이 계정의 태그 전략은 {strategy['count']}개인데 "
                f"{spec.display_name} 상한은 {spec.hashtag_max}개다. "
                f"{spec.hashtag_max}개로 줄였다",
                severity="warning",
            )
        )
        strategy["count"] = spec.hashtag_max

    # ── 플랫폼 문화와의 충돌은 조용히 덮지 않는다 ───────────────────────
    if spec.emoji_density == "high" and float(dna["copy"]["emoji_density"]) == 0:
        warnings.append(
            Violation(
                "copy.emoji_density",
                f"{spec.display_name}은 이모지를 많이 쓰는 문화인데 이 계정은 "
                "이모지를 쓰지 않는다. StyleDNA를 하드 제약으로 두므로 이모지 없이 "
                "간다 — 문화에 맞추려면 사람이 DNA를 고쳐야 한다",
                severity="warning",
            )
        )
    return out, warnings


def _retarget_limits(
    source_copy: dict[str, Any],
    pair: LocalizationPair,
    capacity: dict[str, RoleCapacity] | None,
) -> tuple[dict[str, int], list[Violation]]:
    """글자수 상한 재산출.

    두 개의 상한이 있고 작은 쪽이 이긴다.

      문체 상한  원본 상한 × 언어 밀도 비율. 계정이 얼마나 짧게 쓰는가.
      물리 상한  안전영역에 실제로 들어가는 글자 수 (실측).
    """
    out: dict[str, int] = {}
    warnings: list[Violation] = []
    for field_name, role in (
        ("headline_char_limit", "headline"),
        ("body_char_limit_per_slide", "body"),
    ):
        scaled = max(1, int(int(source_copy[field_name]) * pair.hard_ratio))
        limit = scaled
        cap = (capacity or {}).get(role)
        if cap is not None and cap.chars < scaled:
            limit = cap.chars
            warnings.append(
                Violation(
                    f"copy.{field_name}",
                    f"문체 상한 {scaled}자보다 실측 수용량 {cap.chars}자가 작아 "
                    f"{cap.chars}자로 내렸다 ({cap})",
                    severity="warning",
                )
            )
        out[field_name] = limit
    return out, warnings


# ── 에이전트 ────────────────────────────────────────────────────────────

_SYSTEM = """너는 한 계정의 콘텐츠를 다른 언어권으로 옮기는 현지화 담당자다.

**번역가가 아니다.** 원문의 문장 구조를 따라가면 실패다. 원문이 전하려는 메시지를
붙잡고, 도착 언어 독자가 처음부터 그 언어로 썼을 법한 문장을 새로 쓴다.

- 원문에 있는 비유·관용구는 도착 언어의 대응물로 바꾼다. 대응물이 없으면 풀어 쓴다.
- 한자어를 그대로 옮기면 뜻이 어긋나는 경우가 많다. 의미를 먼저 확인해라.
- **글자수 상한은 하드 제약이다.** 넘긴 카피는 버려진다.
- 블록 id는 원본 그대로 둔다. 블록을 늘리거나 없애지 않는다 — 레이아웃이 정해져 있다.
- 근거 없는 숫자·통계·연도를 새로 만들지 마라. 원문에 없던 숫자를 넣지 않는다.
"""


class Localizer(Agent):
    name = "A10 Localizer"
    stage = PipelineStage.LOCALIZE
    milestone = "M7"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("drafting")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        target_platform = ctx.options.get("target_platform")
        target_language = ctx.options.get("target_language")
        if not target_platform or not target_language:
            raise LocalizationError(
                "현지화 대상이 지정되지 않았다. AgentContext.options에 "
                "target_platform / target_language를 넣어라."
            )
        result = self.localize(
            state["copy"],
            ctx,
            target_platform=target_platform,
            target_language=target_language,
            parent_set_id=state.get("set_id"),
            capacity=ctx.options.get("capacity"),
        )
        return {**state, "localized": result.as_dict()}

    # ── 본체 ────────────────────────────────────────────────────────────
    def localize(
        self,
        copy: dict[str, Any],
        ctx: AgentContext,
        *,
        target_platform: str,
        target_language: str,
        parent_set_id: str | None = None,
        capacity: dict[str, RoleCapacity] | None = None,
    ) -> LocalizationResult:
        dna = ctx.style_dna
        if dna is None:
            raise LocalizationError(
                "StyleDNA 없이는 현지화할 수 없다 — 글자수와 폰트가 하드 제약이다"
            )
        source_language = dna["copy"]["language"]
        if source_language == target_language and ctx.platform == target_platform:
            raise LocalizationError(
                f"출발과 도착이 같다 ({source_language}/{ctx.platform}). "
                "현지화할 것이 없다."
            )
        pair = localization_pair(source_language, target_language)
        spec = platform_spec(target_platform)
        adapter = adapter_for(target_platform)

        target_dna, warnings = retarget_dna(
            dna,
            target_language=target_language,
            target_platform=target_platform,
            capacity=capacity,
        )
        constraints = CopyConstraints.from_dna(target_dna, spec)

        count = adapter.check_slide_count(len(copy["slides"]))
        if not count.ok:
            raise LocalizationError(
                f"원본 {len(copy['slides'])}장이 {spec.display_name} 규격에 맞지 않는다:\n  - "
                + "\n  - ".join(count.problems)
            )

        caption_rules = CaptionConstraints.from_dna(target_dna, spec)
        draft = self._draft(copy, dna, target_dna, pair, spec, constraints, caption_rules)
        slides, attempts = self._enforce(draft, copy, constraints, pair, spec)

        hashtags, research = self._research_hashtags(copy, dna, target_dna, pair, spec, ctx)
        caption, caption_warnings = self._check_caption(
            draft.caption, hashtags, target_dna, spec, adapter
        )
        warnings += caption_warnings

        # 커버 정보 밀도는 규격이 아니라 문화다. 막지 않고 기록만 남긴다.
        cover = next((s for s in slides if s["index"] == 1), None)
        if cover is not None:
            density = adapter.check_cover_density(cover["copy_blocks"])
            warnings += [
                Violation("cover", problem, severity="warning")
                for problem in density.problems
            ]

        target_dna["copy"]["register"] = draft.target_register
        if draft.signature_phrases:
            target_dna["copy"]["signature_phrases"] = draft.signature_phrases

        return LocalizationResult(
            platform=target_platform,
            language=target_language,
            style_dna=target_dna,
            copy={
                "slides": slides,
                "caption": caption,
                "hashtags": hashtags,
                "template_swaps": {},
                "warnings": [str(w) for w in warnings],
                "attempts": attempts,
            },
            parent_set_id=parent_set_id,
            capacity=capacity or {},
            hashtag_research=[t.model_dump() for t in research],
            notes=list(draft.notes),
            warnings=warnings,
            attempts=attempts,
        )

    # ── 카피 ────────────────────────────────────────────────────────────
    def _brief(
        self,
        constraints: CopyConstraints,
        caption_rules: CaptionConstraints,
        pair: LocalizationPair,
        spec: Any,
        source_copy: dict[str, Any],
    ) -> str:
        target = language_spec(pair.target)
        source = language_spec(pair.source)
        lines = [
            f"- 출발 언어: {source.display_name} → 도착 언어: {target.display_name}",
            f"- {target.display_name} 말투에 대해: {target.register_note}",
            f"  (원본 말투는 '{source_copy['register']}'다. 이름을 옮기지 말고 "
            f"같은 인상을 주는 {target.display_name} 말투를 골라라)",
            f"- 길이 목표: 원문의 {int(pair.char_ratio[0] * 100)}~"
            f"{int(pair.char_ratio[1] * 100)}%. 그보다 길면 직역했다는 뜻이다.",
            f"- 헤드라인 상한: {constraints.headline_char_limit}자 (하드 제약)",
            f"- 본문 상한: {constraints.body_char_limit}자 (하드 제약)",
        ]
        if constraints.cover_title_limit:
            lines.append(
                f"- **커버(1번 슬라이드) 헤드라인은 {constraints.cover_title_limit}자를 "
                f"넘으면 피드에서 잘린다.** 가장 빡빡한 제약이다."
            )
        if constraints.emoji_density == 0:
            lines.append("- **이모지를 쓰지 않는다.** 도착 플랫폼 문화와 무관하게 하나도 넣지 마라.")
        else:
            lines.append(
                f"- 이모지 밀도 {constraints.emoji_density}, "
                f"쓸 수 있는 이모지: {''.join(constraints.emoji_palette)}"
            )
        lines.append(f"- 플랫폼 문화: {spec.culture_prompt}")
        lines.append(f"- 현지화 지침: {pair.guidance}")
        lines += [
            "",
            "캡션 제약:",
            f"- 첫 줄(hook_line)은 {caption_rules.fold_at}자 안에서 끝난다. "
            "여기서 잘리면 훅이 사라진다.",
            f"- hook_line + body + cta 합계는 {caption_rules.length_min}~"
            f"{caption_rules.length_max}자.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_source(copy: dict[str, Any]) -> str:
        lines = []
        for slide in copy["slides"]:
            lines.append(f"슬라이드 {slide['index']} [{slide['role']}]")
            for block in slide["copy_blocks"]:
                text = block["text"].replace("\n", "⏎")
                lines.append(f"  {block['id']} ({block['role']}): {text}")
        caption = copy["caption"]
        lines.append("캡션:")
        lines.append(f"  hook_line: {caption['hook_line']}")
        lines.append(f"  body: {caption['body']}")
        lines.append(f"  cta: {caption['cta']}")
        return "\n".join(lines)

    def _draft(
        self,
        copy: dict[str, Any],
        dna: dict[str, Any],
        target_dna: dict[str, Any],
        pair: LocalizationPair,
        spec: Any,
        constraints: CopyConstraints,
        caption_rules: CaptionConstraints,
    ) -> LocalizedCopy:
        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"계정: {dna['identity']['one_line']}\n"
                f"독자: {dna['identity']['target_reader']}\n\n"
                f"제약:\n{self._brief(constraints, caption_rules, pair, spec, dna['copy'])}\n\n"
                f"원문:\n{self._render_source(copy)}\n\n"
                "블록 id를 그대로 두고 각 블록의 도착 언어 문장을 써라. "
                "해시태그는 여기서 쓰지 마라 — 따로 조사한다."
            ),
            output_model=LocalizedCopy,
            profile="drafting",
        )
        return result.parsed

    def _enforce(
        self,
        draft: LocalizedCopy,
        source: dict[str, Any],
        constraints: CopyConstraints,
        pair: LocalizationPair,
        spec: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """제약을 세어 보고 넘치면 축약을 요청한다. 소진되면 명시적으로 실패한다."""
        expected = {
            b["id"]: (slide["index"], b["role"])
            for slide in source["slides"]
            for b in slide["copy_blocks"]
        }
        texts = self._flatten(draft)
        attempt = 1

        while True:
            missing = sorted(set(expected) - set(texts))
            if missing:
                raise LocalizationError(
                    f"현지화 결과에 원본 블록이 빠졌다: {', '.join(missing)}. "
                    "레이아웃이 정해져 있어 블록이 사라지면 빈 자리가 남는다."
                )
            unknown = sorted(set(texts) - set(expected))
            if unknown:
                raise LocalizationError(
                    f"원본에 없는 블록 id가 생겼다: {', '.join(unknown)}"
                )

            failures = self._violations(texts, expected, constraints)
            if not failures:
                break
            if attempt > MAX_SHRINK_ATTEMPTS:
                raise LocalizationError(
                    f"현지화 카피가 {MAX_SHRINK_ATTEMPTS}회 축약 후에도 제약을 넘는다. "
                    "조용히 통과시키지 않는다:\n" + describe([v for _, v in failures])
                )
            texts = self._shrink(texts, failures, constraints, pair, attempt)
            attempt += 1

        out = []
        emphasis = {b.id: b.emphasis_spans for slide in draft.slides for b in slide.blocks}
        for slide in source["slides"]:
            blocks = []
            for block in slide["copy_blocks"]:
                text = texts[block["id"]]
                spans = [
                    list(s)
                    for s in emphasis.get(block["id"], [])
                    if len(s) == 2 and 0 <= s[0] < s[1] <= len(text)
                ]
                blocks.append(
                    {
                        "id": block["id"],
                        "role": block["role"],
                        "text": text,
                        "max_chars": constraints.limit_for(block["role"]),
                        "emphasis_spans": spans,
                        "editable": True,
                    }
                )
            out.append(
                {
                    "index": slide["index"],
                    "role": slide["role"],
                    "layout_template": slide["layout_template"],
                    "copy_blocks": blocks,
                }
            )
        return out, attempt

    @staticmethod
    def _flatten(draft: LocalizedCopy) -> dict[str, str]:
        return {b.id: b.text for slide in draft.slides for b in slide.blocks}

    @staticmethod
    def _violations(
        texts: dict[str, str],
        expected: dict[str, tuple[int, str]],
        constraints: CopyConstraints,
    ) -> list[tuple[str, Violation]]:
        out: list[tuple[str, Violation]] = []
        for block_id, text in texts.items():
            index, role = expected[block_id]
            checks = constraints.check_text(text, field_name=block_id, role=role)
            if index == 1 and role == "headline":
                checks += constraints.check_cover_title(text, field_name=block_id)
            for v in blocking(checks):
                out.append((block_id, v))
        return out

    def _shrink(
        self,
        texts: dict[str, str],
        failures: list[tuple[str, Violation]],
        constraints: CopyConstraints,
        pair: LocalizationPair,
        attempt: int,
    ) -> dict[str, str]:
        broken = sorted({block_id for block_id, _ in failures})
        detail = "\n".join(str(v) for _, v in failures)
        target = language_spec(pair.target)

        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"아래 {target.display_name} 카피가 제약을 어겼다 ({attempt}번째 수정 요청).\n\n"
                f"위반 내역:\n{detail}\n\n"
                f"현재 카피:\n"
                + "\n".join(f"  {bid}: {texts[bid]}" for bid in broken)
                + "\n\n"
                "**줄여라.** 의미의 핵은 남기고 수식을 덜어낸다. 원문으로 돌아가서 "
                "다시 직역하지 마라 — 지금 문장을 짧게 만드는 일이다.\n"
                "지적된 블록만 다시 써라. 다른 블록은 그대로 둔다."
            ),
            output_model=LocalizedCopy,
            profile="drafting",
        )
        updated = dict(texts)
        for block in self._flatten(result.parsed).items():
            block_id, text = block
            if block_id in updated:
                updated[block_id] = text
        return updated

    # ── 캡션 ────────────────────────────────────────────────────────────
    def _check_caption(
        self,
        caption: Caption,
        hashtags: list[str],
        target_dna: dict[str, Any],
        spec: Any,
        adapter: Any,
    ) -> tuple[dict[str, Any], list[Violation]]:
        rules = CaptionConstraints.from_dna(target_dna, spec)
        violations = rules.check(caption.hook_line, caption.body, caption.cta, hashtags)

        # 조립된 캡션 길이를 따로 잰다. `CaptionConstraints.check`는 본문 세 토막만
        # 세는데, 话题 표기(`#태그[话题]#`)는 태그마다 글자를 더한다. 본문만 재면
        # 상한 안이어도 실제로 올라가는 글은 넘칠 수 있다.
        assembled = adapter.assemble_caption(
            caption.hook_line, caption.body, caption.cta, hashtags
        )
        total = visible_length(assembled)
        if total > spec.caption_max_chars:
            violations.append(
                Violation(
                    "caption.assembled",
                    f"태그 표기까지 붙인 캡션이 {total}자로 플랫폼 상한 "
                    f"{spec.caption_max_chars}자를 넘는다",
                )
            )

        hard = blocking(violations)
        if hard:
            raise LocalizationError(
                "현지화된 캡션이 제약을 어겼다:\n" + describe(hard)
            )
        return caption.model_dump(), [v for v in violations if v.severity == "warning"]

    # ── 해시태그 재조사 ─────────────────────────────────────────────────
    def _research_hashtags(
        self,
        copy: dict[str, Any],
        dna: dict[str, Any],
        target_dna: dict[str, Any],
        pair: LocalizationPair,
        spec: Any,
        ctx: AgentContext,
    ) -> tuple[list[str], list[ResearchedTag]]:
        """번역이 아니라 조사다. 검색이 실제로 돌지 않으면 실패한다."""
        strategy = target_dna["caption"]["hashtag_strategy"]
        target = language_spec(pair.target)
        lo, hi = spec.hashtag_recommended
        want = min(int(strategy["count"]), spec.hashtag_max)

        result = self.llm.structured(
            system=(
                "너는 해당 언어권 소셜 플랫폼의 태그 사용 실태를 조사하는 사람이다. "
                "기억으로 답하지 말고 검색해서 확인해라. 실제로 쓰이지 않는 태그를 "
                "그럴듯하게 지어내면 이 작업은 실패다."
            ),
            user=(
                f"플랫폼: {spec.display_name}\n"
                f"언어권: {target.display_name}\n"
                f"주제: {copy['caption']['hook_line']}\n"
                f"슬라이드 요지: "
                f"{[b['text'] for s in copy['slides'] for b in s['copy_blocks'] if b['role'] == 'headline']}\n"
                f"원본({language_spec(pair.source).display_name}) 해시태그: "
                f"{', '.join(copy.get('hashtags', []))}\n\n"
                f"{pair.hashtag_note}\n\n"
                f"이 주제로 {spec.display_name}에서 실제 쓰이는 태그를 정확히 {want}개 "
                f"조사해라 (플랫폼 상한 {spec.hashtag_max}개, 권장 {lo}~{hi}개).\n"
                f"구성: 넓은 태그 {strategy['mix']['broad']}, 니치 {strategy['mix']['niche']}, "
                f"브랜드 {strategy['mix']['branded']}, 커뮤니티 {strategy['mix']['community']}.\n"
                "각 태그마다 실제로 쓰인다고 판단한 근거를 적어라. "
                "위 원본 태그를 그대로 번역한 것은 답이 아니다."
            ),
            output_model=HashtagSet,
            profile="drafting",
            search=True,
        )
        if not result.search_hits:
            raise LocalizationError(
                "해시태그를 재조사하지 못했다 — 검색이 페이지를 하나도 열지 않았다. "
                "원본 태그를 직역해서 넘기지 않는다 (검색량이 사실상 0인 태그가 된다)."
            )

        tags: list[str] = []
        for tag in result.parsed.tags:
            value = tag.tag if tag.tag.startswith("#") else f"#{tag.tag}"
            if value not in tags:
                tags.append(value)
        return tags[: spec.hashtag_max], result.parsed.tags


def cover_title_of(copy: dict[str, Any]) -> str | None:
    """1번 슬라이드의 헤드라인. 플랫폼이 제목으로 잘라 보는 자리다."""
    for slide in copy["slides"]:
        if slide["index"] != 1:
            continue
        for block in slide["copy_blocks"]:
            if block["role"] == "headline":
                return block["text"]
    return None


def cover_title_report(copy: dict[str, Any], platform: str) -> list[str]:
    """커버 제목이 플랫폼 상한에 걸리는지. 넘으면 사람이 보게 문장으로 남긴다."""
    title = cover_title_of(copy)
    if title is None:
        return ["1번 슬라이드에 headline 블록이 없다 — 커버 제목을 확인할 수 없다"]
    check = adapter_for(platform).check_cover_title(title.replace("\n", ""))
    if check.ok:
        limit = platform_spec(platform).title_max_chars
        if limit is None:
            return []
        return [f"커버 제목 {visible_length(title)}자 / 상한 {limit}자 — 통과"]
    return check.problems
