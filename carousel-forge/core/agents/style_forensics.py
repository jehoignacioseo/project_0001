"""A1 StyleForensics — 벤치마크 계정의 스타일 DNA 역설계.

스타일 벤치마킹의 성패는 "무엇을 추출할지의 해상도"에 달려 있다. 그래서 이
에이전트는 두 층으로 나뉜다.

  **측정 층** (`core.agents.forensics`) — 색은 픽셀 k-means에서, 텍스트 영역은
  경사 기하에서, 어미·이모지·해시태그는 캡션 통계에서 **센다**.
  **해석 층** (여기) — 잰 값을 모델에게 함께 주고, 세지 못하는 것(아키타입, 서사
  패턴, 훅 공식, 금지어)을 채우게 한다.

순서가 중요하다. 모델에게 먼저 물어보고 나중에 검산하는 게 아니라, **잰 값을
쥐여 주고** 그 위에서 해석하게 한다. 측정 가능한 필드는 모델이 뭐라고 답하든
측정값으로 덮어쓴다 — 눈대중이 픽셀을 이길 이유가 없다.

추출 후에는 **검증 렌더**가 남아 있다. 더미 주제로 3장을 뽑아 원본 피드와 나란히
놓고, 사용자가 "닮았다"고 승인해야 `is_active=True`가 된다 (`preview.py`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from apps.api.models import PipelineStage
from apps.api.schemas.generated.style_dna import (
    Alignment,
    Archetype,
    Case,
    CoverRule,
    CtaType,
    Decoration,
    Grid,
    HookType,
    NarrativePattern,
    SlideRole,
    StyleDNA,
    TreatmentEnum,
    Type as OverlayType,
)
from core.agents.base import Agent, AgentContext
from core.agents.forensics import (
    CaptionStats,
    PaletteReport,
    ZoneReport,
    analyse_captions,
    analyse_text_zones,
    extract_palette,
)
from core.config import SCHEMAS_DIR, platform_spec
from core.providers.llm import LLMClient, default_client

#: 스펙의 추출 규칙: 최소 6장, 권장 12장 이상.
MIN_SAMPLES = 6
RECOMMENDED_SAMPLES = 12

#: 한 번에 모델에 넣는 이미지 수. 너무 많이 넣으면 개별 장의 신호가 묻힌다.
MAX_IMAGES_TO_MODEL = 12

#: 폰트는 정확 식별이 어렵다. "유사 계열 + 실제로 임베드 가능한 대체 폰트" 쌍으로 저장한다.
FALLBACK_CHAINS: dict[str, list[str]] = {
    "sans": ["Pretendard", "Noto Sans KR", "sans-serif"],
    "serif": ["Noto Serif KR", "serif"],
}


class ForensicsError(RuntimeError):
    """스타일을 추출할 수 없다."""


class Interpretation(BaseModel):
    """모델이 채우는 부분 — 세어서는 알 수 없는 것들만 묻는다.

    열거형 필드는 스키마에서 생성된 enum을 그대로 쓴다. 설명에 선택지를 적어 두고
    지키기를 바라는 대신, 구조화 출력이 애초에 다른 값을 못 내게 막는 편이 낫다.
    """

    archetype: Archetype
    one_line: str = Field(description="이 계정을 한 문장으로")
    target_reader: str = Field(description="누가 이걸 저장하는가")

    headline_family_class: Literal["sans", "serif"]
    headline_weight: int = Field(ge=100, le=900)
    headline_size_ratio: float = Field(gt=0, le=0.3, description="캔버스 짧은 변 대비 비율")
    headline_letter_spacing_em: float
    headline_line_height: float = Field(gt=0)
    headline_case: Case
    body_size_ratio: float = Field(gt=0, le=0.2)
    body_line_height: float = Field(gt=0)
    accent_size_ratio: float = Field(gt=0, le=0.2)
    mixed_script_rule: str

    text_block_max_lines: int = Field(ge=1, le=12)
    grid: Grid
    decorations: list[Decoration] = Field(description="관찰된 장식만 넣는다. 없으면 빈 목록")

    photo_ratio: float = Field(ge=0, le=1)
    illustration_ratio: float = Field(ge=0, le=1)
    solid_ratio: float = Field(ge=0, le=1)
    treatment: list[TreatmentEnum] = Field(description="관찰된 후보정만. 없으면 빈 목록")
    grain_intensity: float = Field(ge=0, le=1)
    subject_rules: str = Field(description="인물 등장 여부, 손/제품 등장 방식, 크롭 습관")
    overlay_type: OverlayType
    overlay_opacity: float = Field(ge=0, le=1)

    slide_count_min: int = Field(ge=1, le=20)
    slide_count_max: int = Field(ge=1, le=20)
    slide_count_mode: int = Field(ge=1, le=20)
    hook_type: HookType
    narrative_pattern: NarrativePattern
    slide_roles_sequence: list[SlideRole]
    cta_type: CtaType
    cover_rule: CoverRule

    headline_char_limit: int = Field(ge=1, le=200)
    body_char_limit_per_slide: int = Field(ge=1, le=400)
    signature_phrases: list[str]
    forbidden_words: list[str] = Field(description="이 계정이 절대 안 쓸 법한 말")

    first_line_rule: str
    hashtag_broad: int = Field(ge=0)
    hashtag_niche: int = Field(ge=0)
    hashtag_branded: int = Field(ge=0)
    hashtag_community: int = Field(ge=0)

    notes: str = Field(description="추출 근거 메모")
    low_confidence_fields: list[str] = Field(description="샘플 부족으로 추정한 필드")


@dataclass
class ForensicsResult:
    dna: dict[str, Any]
    confidence_score: float
    warnings: list[str] = field(default_factory=list)
    palette: PaletteReport | None = None
    zones: ZoneReport | None = None
    captions: CaptionStats | None = None
    sample_count: int = 0

    def report(self) -> str:
        """사람이 읽는 요약 리포트."""
        dna = self.dna
        lines = [
            "═" * 58,
            f"  StyleDNA — {dna['identity']['archetype']}",
            "═" * 58,
            f"  {dna['identity']['one_line']}",
            f"  독자: {dna['identity']['target_reader']}",
            "",
            f"  신뢰도: {self.confidence_score:.2f}  (샘플 {self.sample_count}장)",
        ]
        for warning in self.warnings:
            lines.append(f"  ⚠ {warning}")

        palette = dna["visual"]["palette"]
        lines += [
            "",
            "── 팔레트 (픽셀 k-means, k=6) ──",
            f"  배경 {palette['background'][0]}   텍스트 {palette['text'][0]}   "
            f"액센트 {palette['accent'][0]}",
            f"  비중 {palette['usage_ratio']}",
        ]
        if self.palette:
            lines.append(
                "  전체 군집: "
                + "  ".join(f"{s.hex}({s.share:.0%})" for s in self.palette.swatches)
            )

        typo = dna["visual"]["typography"]
        layout = dna["visual"]["layout"]
        lines += [
            "",
            "── 타이포 · 레이아웃 ──",
            f"  헤드라인 {typo['headline']['family']} {typo['headline']['weight']} "
            f"· 크기비 {typo['headline']['size_ratio']} · 자간 {typo['headline']['letter_spacing_em']}em",
            f"  본문 {typo['body']['family']} · 크기비 {typo['body']['size_ratio']}",
            f"  텍스트존 {layout['text_zone']} · 정렬 {layout['alignment']} "
            f"· 여백비 {layout['safe_margin_ratio']}",
            f"  장식 {layout['decorations'] or '없음'}",
        ]

        structure = dna["structure"]
        copy = dna["copy"]
        lines += [
            "",
            "── 구조 · 카피 ──",
            f"  {structure['slide_count_range'][0]}~{structure['slide_count_range'][1]}장 "
            f"(주로 {structure['slide_count_mode']}장) · {structure['narrative_pattern']}",
            f"  훅 {structure['hook_type']} · CTA {structure['cta_type']} · 커버 {structure['cover_rule']}",
            f"  role 순서 {structure['slide_roles_sequence']}",
            f"  말투 {copy['register']} · 헤드라인 {copy['headline_char_limit']}자 "
            f"· 본문 {copy['body_char_limit_per_slide']}자",
            f"  이모지 밀도 {copy['emoji_density']}"
            + (f" {''.join(copy['emoji_palette'])}" if copy["emoji_palette"] else " (쓰지 않음)"),
            f"  금지어 {copy['forbidden_words'] or '없음'}",
            f"  시그니처 {copy['signature_phrases'] or '없음'}",
        ]

        evidence = dna["evidence"]
        if evidence["low_confidence_fields"]:
            lines += ["", "── 신뢰도 낮은 필드 ──"]
            lines += [f"  · {f}" for f in evidence["low_confidence_fields"]]

        lines += ["", "═" * 58,
                  "  다음 단계: 검증 렌더를 원본과 나란히 보고 승인해야 활성화된다.",
                  "═" * 58]
        return "\n".join(lines)


_SYSTEM = """너는 인스타그램/샤오홍슈 계정의 시각·카피 스타일을 해체 분석하는 아트디렉터다.

**측정된 값이 함께 주어진다.** 색·텍스트 영역·여백·어미·이모지 밀도·해시태그 수는
이미 픽셀과 통계에서 뽑은 값이다. 그 값과 다르게 보이더라도 측정값을 의심하지 말고,
너는 **세어서는 알 수 없는 것**에 집중해라 — 아키타입, 서사 패턴, 훅 공식, 크롭 습관,
이 계정이 절대 쓰지 않을 법한 말 같은 것들.

주의:
- 근거가 약한 필드는 반드시 low_confidence_fields에 올려라. 확신하는 척하지 마라.
- forbidden_words는 이 계정의 톤과 정면으로 어긋나는 말을 적는다. 일반적인 비속어
  목록이 아니라, **이 계정이라서** 안 쓸 말이어야 한다.
- slide_roles_sequence는 hook으로 시작하고 cta로 끝난다.
- size_ratio는 캔버스 짧은 변 대비 비율이다. 헤드라인이 화면 폭의 몇 분의 일을
  차지하는지 보고 역산해라 (예: 한 줄에 8글자가 들어가면 대략 0.09).
"""


class StyleForensics(Agent):
    name = "A1 StyleForensics"
    stage = PipelineStage.STYLE_RESOLVE
    milestone = "M3"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("reasoning")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        result = self.extract(
            [Path(p) for p in state["screenshots"]],
            captions=state.get("captions") or [],
            ctx=ctx,
        )
        return {
            **state,
            "style_dna": result.dna,
            "confidence_score": result.confidence_score,
            "forensics_warnings": result.warnings,
            "forensics_report": result.report(),
        }

    def extract(
        self, screenshots: list[Path], *, captions: list[str], ctx: AgentContext
    ) -> ForensicsResult:
        if not screenshots:
            raise ForensicsError("스크린샷이 없다")
        missing = [p for p in screenshots if not p.exists()]
        if missing:
            raise ForensicsError(f"파일을 찾을 수 없다: {missing}")

        warnings: list[str] = []
        count = len(screenshots)
        if count < MIN_SAMPLES:
            warnings.append(
                f"샘플이 {count}장이다. 최소 {MIN_SAMPLES}장, 권장 {RECOMMENDED_SAMPLES}장 "
                "이상에서 추출해야 한다 — 이 DNA는 신뢰도가 낮다."
            )
        elif count < RECOMMENDED_SAMPLES:
            warnings.append(
                f"샘플이 {count}장이다. {RECOMMENDED_SAMPLES}장 이상이면 더 안정적이다."
            )

        # ── 측정 ────────────────────────────────────────────────────────
        palette = extract_palette(screenshots)
        zones = analyse_text_zones(screenshots)
        stats = analyse_captions(captions) if captions else None
        if stats is None:
            warnings.append(
                "캡션이 주어지지 않아 말투·이모지 밀도·해시태그 전략을 세지 못했다. "
                "모델 추정값이므로 신뢰도가 낮다."
            )
        if zones.samples == 0:
            warnings.append("텍스트 영역이 잡히지 않았다 — 여백·정렬은 기본값이다.")

        # ── 해석 ────────────────────────────────────────────────────────
        interpretation = self._interpret(screenshots, palette, zones, stats, captions, ctx)
        dna = self._assemble(interpretation, palette, zones, stats, ctx, count)
        confidence = self._confidence(count, zones, stats, interpretation)

        self._validate(dna)
        return ForensicsResult(
            dna=dna,
            confidence_score=confidence,
            warnings=warnings,
            palette=palette,
            zones=zones,
            captions=stats,
            sample_count=count,
        )

    # ── 내부 ────────────────────────────────────────────────────────────
    def _interpret(
        self,
        screenshots: list[Path],
        palette: PaletteReport,
        zones: ZoneReport,
        stats: CaptionStats | None,
        captions: list[str],
        ctx: AgentContext,
    ) -> Interpretation:
        spec = platform_spec(ctx.platform)
        measured = [
            "── 픽셀에서 잰 값 (k-means, k=6) ──",
            f"배경 {palette.background.hex} ({palette.background.share:.0%})",
            f"텍스트 {palette.text.hex}   액센트 {palette.accent.hex}",
            "전체 군집: " + ", ".join(f"{s.hex} {s.share:.0%}" for s in palette.swatches),
            "",
            "── 기하에서 잰 값 ──",
            f"텍스트존 {zones.text_zone} (띠 {zones.ink_top:.2f}~{zones.ink_bottom:.2f})",
            f"여백비 {zones.safe_margin_ratio} · 정렬 {zones.alignment}",
            f"잉크 밀도 {zones.ink_coverage:.2f} → 커버 정보 밀도 {zones.cover_info_density}",
        ]
        if stats:
            measured += [
                "",
                "── 캡션 통계에서 잰 값 ──",
                f"말투 {stats.register} (확신 {stats.register_confidence:.0%})",
                f"문장 평균 {stats.sentence_length_avg:.0f}자 · 캡션 길이 "
                f"{stats.caption_length_range[0]}~{stats.caption_length_range[1]}자",
                f"이모지 밀도 {stats.emoji_density:.4f} "
                + (f"팔레트 {''.join(stats.emoji_palette)}" if stats.emoji_palette else "(이모지 없음)"),
                f"해시태그 평균 {stats.hashtag_count_avg:.1f}개 · 배치 {stats.hashtag_placement}",
                f"문장부호 습관: {stats.punctuation_habits}",
                f"반복 구문: {', '.join(stats.repeated_phrases) or '없음'}",
            ]

        sample_captions = "\n---\n".join(captions[:6]) if captions else "(캡션이 제공되지 않았다)"
        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"플랫폼: {spec.display_name} · 캔버스 {spec.canvas.width}×{spec.canvas.height}\n"
                f"샘플 {len(screenshots)}장\n\n"
                + "\n".join(measured)
                + f"\n\n── 캡션 원문 (일부) ──\n{sample_captions}\n\n"
                "이 계정의 스타일 DNA에서 **세어서는 알 수 없는 부분**을 채워라."
            ),
            output_model=Interpretation,
            images=screenshots[:MAX_IMAGES_TO_MODEL],
            profile="reasoning",
        )
        return result.parsed

    def _assemble(
        self,
        it: Interpretation,
        palette: PaletteReport,
        zones: ZoneReport,
        stats: CaptionStats | None,
        ctx: AgentContext,
        sample_count: int,
    ) -> dict[str, Any]:
        """측정값이 이긴다. 모델이 다르게 답했어도 잰 값으로 덮어쓴다."""
        chain = FALLBACK_CHAINS.get(it.headline_family_class, FALLBACK_CHAINS["sans"])
        family, fallback = chain[0], chain[1:]

        mix_total = it.photo_ratio + it.illustration_ratio + it.solid_ratio or 1.0
        roles = [str(r) for r in it.slide_roles_sequence]
        if not roles or roles[0] != "hook":
            roles = ["hook", *[r for r in roles if r != "hook"]]
        if roles[-1] != "cta":
            roles = [*[r for r in roles if r != "cta"], "cta"]

        lo, hi = sorted((it.slide_count_min, it.slide_count_max))
        mode = min(max(it.slide_count_mode, lo), hi)

        copy_stats = stats.as_dna_fragments() if stats else {"copy": {}, "caption": {}}

        return {
            "identity": {
                "archetype": str(it.archetype),
                "one_line": it.one_line,
                "target_reader": it.target_reader,
            },
            "visual": {
                "palette": {
                    # ← 픽셀에서 잰 값
                    "primary": [palette.text.hex],
                    "accent": [palette.accent.hex],
                    "background": [palette.background.hex],
                    "text": [palette.text.hex],
                    "usage_ratio": palette.usage_ratio(),
                },
                "typography": {
                    "headline": {
                        "family": family,
                        "fallback": fallback,
                        "weight": it.headline_weight,
                        "size_ratio": round(it.headline_size_ratio, 4),
                        "letter_spacing_em": round(it.headline_letter_spacing_em, 4),
                        "line_height": round(it.headline_line_height, 3),
                        "case": str(it.headline_case),
                    },
                    "body": {
                        "family": family,
                        "fallback": fallback,
                        "weight": 400,
                        "size_ratio": round(it.body_size_ratio, 4),
                        "line_height": round(it.body_line_height, 3),
                    },
                    "accent": {
                        "family": family,
                        "fallback": fallback,
                        "weight": 700,
                        "size_ratio": round(it.accent_size_ratio, 4),
                    },
                    "korean_font": family,
                    "chinese_font": "Noto Sans SC",
                    "latin_font": family,
                    "mixed_script_rule": it.mixed_script_rule,
                },
                "layout": {
                    # ← 기하에서 잰 값
                    "safe_margin_ratio": zones.safe_margin_ratio,
                    "text_zone": zones.text_zone,
                    "text_block_max_lines": it.text_block_max_lines,
                    "alignment": zones.alignment,
                    "grid": str(it.grid),
                    "decorations": [str(d) for d in it.decorations],
                },
                "imagery": {
                    "type_mix": {
                        "photo": round(it.photo_ratio / mix_total, 3),
                        "illustration": round(it.illustration_ratio / mix_total, 3),
                        "solid_or_gradient": round(it.solid_ratio / mix_total, 3),
                    },
                    "treatment": [str(t) for t in it.treatment],
                    "grain_intensity": round(it.grain_intensity, 3),
                    "subject_rules": it.subject_rules,
                    "overlay": {
                        "type": str(it.overlay_type),
                        "opacity": round(it.overlay_opacity, 3),
                    },
                },
            },
            "structure": {
                "slide_count_range": [lo, hi],
                "slide_count_mode": mode,
                "hook_type": str(it.hook_type),
                "narrative_pattern": str(it.narrative_pattern),
                "slide_roles_sequence": roles,
                "cta_type": str(it.cta_type),
                "cover_rule": str(it.cover_rule),
            },
            "copy": {
                "language": ctx.language,
                # ← 캡션 통계에서 잰 값 (있을 때)
                "register": copy_stats["copy"].get("register", "해요체"),
                "sentence_length_avg": copy_stats["copy"].get("sentence_length_avg", 18),
                "headline_char_limit": it.headline_char_limit,
                "body_char_limit_per_slide": it.body_char_limit_per_slide,
                "emoji_density": copy_stats["copy"].get("emoji_density", 0.0),
                "emoji_palette": copy_stats["copy"].get("emoji_palette", []),
                "punctuation_habits": copy_stats["copy"].get(
                    "punctuation_habits", "관찰된 습관 없음"
                ),
                "signature_phrases": list(stats.repeated_phrases) if stats else it.signature_phrases,
                "forbidden_words": it.forbidden_words,
            },
            "caption": {
                "length_range": copy_stats["caption"].get("length_range", [150, 600]),
                "first_line_rule": it.first_line_rule,
                "structure": ["hook", "body", "line_break", "cta", "hashtag_block"],
                "hashtag_strategy": {
                    "count": copy_stats["caption"].get(
                        "hashtag_count",
                        it.hashtag_broad + it.hashtag_niche + it.hashtag_branded + it.hashtag_community,
                    ),
                    "mix": {
                        "broad": it.hashtag_broad,
                        "niche": it.hashtag_niche,
                        "branded": it.hashtag_branded,
                        "community": it.hashtag_community,
                    },
                    "placement": copy_stats["caption"].get("placement", "end"),
                },
            },
            "evidence": {
                "sampled_posts": sample_count,
                "notes": it.notes,
                "low_confidence_fields": it.low_confidence_fields,
            },
        }

    def _confidence(
        self,
        sample_count: int,
        zones: ZoneReport,
        stats: CaptionStats | None,
        it: Interpretation,
    ) -> float:
        """샘플 6장 미만이면 0.6을 넘지 못한다 (스펙의 추출 규칙)."""
        if sample_count < MIN_SAMPLES:
            base = 0.55 * (sample_count / MIN_SAMPLES)
        else:
            span = RECOMMENDED_SAMPLES - MIN_SAMPLES
            grown = min(sample_count - MIN_SAMPLES, span) / span
            base = 0.60 + 0.25 * grown

        if stats is None:
            base -= 0.12                      # 말투·이모지·해시태그가 추정값이다
        elif stats.register_confidence < 0.6:
            base -= 0.05
        if zones.samples == 0:
            base -= 0.08
        base -= 0.01 * len(it.low_confidence_fields)
        return round(max(0.0, min(base, 0.95)), 3)

    def _validate(self, dna: dict[str, Any]) -> None:
        """계약 위반을 조용히 넘기지 않는다."""
        import jsonschema

        schema = json.loads((SCHEMAS_DIR / "style_dna.schema.json").read_text(encoding="utf-8"))
        try:
            jsonschema.validate(dna, schema)
        except jsonschema.ValidationError as exc:
            location = "/".join(str(p) for p in exc.absolute_path)
            raise ForensicsError(
                f"추출된 StyleDNA가 스키마를 어겼다 ({location}): {exc.message}"
            ) from exc
        StyleDNA.model_validate(dna)
