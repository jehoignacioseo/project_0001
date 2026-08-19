"""파이프라인 상태 머신 정의.

INTAKE → STYLE_RESOLVE → RESEARCH → FACTCHECK → ARCHITECT
   → COPY → VISUAL_GEN → COMPOSE → QUALITY_GATE
        ↘ (fail) ──── RETRY ────↗
   → LOCALIZE(optional) → EXPORT → PERSIST → READY
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.api.models import PipelineStage

#: 기본 진행 순서. LOCALIZE는 선택 단계다.
SEQUENCE: tuple[PipelineStage, ...] = (
    PipelineStage.INTAKE,
    PipelineStage.STYLE_RESOLVE,
    PipelineStage.RESEARCH,
    PipelineStage.FACTCHECK,
    PipelineStage.ARCHITECT,
    PipelineStage.COPY,
    PipelineStage.VISUAL_GEN,
    PipelineStage.COMPOSE,
    PipelineStage.QUALITY_GATE,
    PipelineStage.LOCALIZE,
    PipelineStage.EXPORT,
    PipelineStage.PERSIST,
)

OPTIONAL: frozenset[PipelineStage] = frozenset({PipelineStage.LOCALIZE})

#: QualityGate가 폐기 판정을 내렸을 때 되감을 지점.
#: 실패 종류마다 어디까지 되돌릴지가 다르다.
REWIND_TARGET: dict[str, PipelineStage] = {
    # 전체 인상이 AI 같다는 판정도 결국 배경을 다시 만들어야 풀린다.
    "ai_look": PipelineStage.VISUAL_GEN,
    "ai_text_artifact": PipelineStage.VISUAL_GEN,
    "hand_finger_anomaly": PipelineStage.VISUAL_GEN,
    "identity_drift": PipelineStage.VISUAL_GEN,
    "plastic_skin": PipelineStage.VISUAL_GEN,
    "morphing_artifact": PipelineStage.VISUAL_GEN,
    "contrast_below_wcag": PipelineStage.COMPOSE,
    "text_overflow": PipelineStage.COPY,
    "style_deviation": PipelineStage.COMPOSE,
    "factcheck_false": PipelineStage.COPY,
}


@dataclass(frozen=True)
class Transition:
    frm: PipelineStage
    to: PipelineStage
    reason: str


def next_stage(current: PipelineStage, *, localize: bool = False) -> PipelineStage | None:
    """다음 단계. 마지막 단계면 None(= READY)."""
    idx = SEQUENCE.index(current)
    for stage in SEQUENCE[idx + 1 :]:
        if stage in OPTIONAL and not localize:
            continue
        return stage
    return None


def rewind_for(rule_id: str) -> PipelineStage:
    """폐기 사유에 맞는 되감기 지점. 모르는 사유는 조용히 넘기지 않는다."""
    if rule_id not in REWIND_TARGET:
        raise KeyError(
            f"되감기 지점이 정의되지 않은 폐기 사유: {rule_id!r}. "
            "config/quality_rules.yaml과 states.REWIND_TARGET을 함께 갱신하라."
        )
    return REWIND_TARGET[rule_id]
