"""파이프라인 오케스트레이터 (상태 머신 구동).

M0/M1에서는 단계 등록·순서·되감기 규칙만 성립해 있고, 실제 구동은 참여
에이전트가 붙는 M2 이후에 열린다. 미구현 단계를 만나면 건너뛰지 않고 멈춘다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.api.models import PipelineStage
from core.agents import (
    ArtDirector,
    CopySmith,
    FactChecker,
    LayoutCompositor,
    Localizer,
    NarrativeArchitect,
    QualityGate,
    StyleForensics,
    TopicIntake,
    TrendScout,
)
from core.agents.base import Agent, AgentContext
from core.pipeline import states
from core.pipeline.retry import RetryBudget

AGENTS: dict[PipelineStage, type[Agent]] = {
    PipelineStage.INTAKE: TopicIntake,
    PipelineStage.STYLE_RESOLVE: StyleForensics,
    PipelineStage.RESEARCH: TrendScout,
    PipelineStage.FACTCHECK: FactChecker,
    PipelineStage.ARCHITECT: NarrativeArchitect,
    PipelineStage.COPY: CopySmith,
    PipelineStage.VISUAL_GEN: ArtDirector,
    PipelineStage.COMPOSE: LayoutCompositor,
    PipelineStage.QUALITY_GATE: QualityGate,
    PipelineStage.LOCALIZE: Localizer,
}


@dataclass
class RunResult:
    state: dict[str, Any]
    completed: list[PipelineStage] = field(default_factory=list)
    stopped_at: PipelineStage | None = None
    error: str | None = None


class Orchestrator:
    def __init__(self, ctx: AgentContext, *, localize: bool = False) -> None:
        self.ctx = ctx
        self.localize = localize
        self.budget = RetryBudget.from_config()

    def run(self, state: dict[str, Any], *, start: PipelineStage = PipelineStage.INTAKE) -> RunResult:
        result = RunResult(state=dict(state))
        stage: PipelineStage | None = start
        while stage is not None:
            if stage in (PipelineStage.EXPORT, PipelineStage.PERSIST):
                # 렌더/내보내기·영속화는 에이전트가 아니라 core.render / DB가 맡는다.
                result.completed.append(stage)
                stage = states.next_stage(stage, localize=self.localize)
                continue
            agent = AGENTS[stage]()
            try:
                result.state = agent.run(result.state, self.ctx)
            except NotImplementedError as exc:
                result.stopped_at = stage
                result.error = str(exc)
                return result
            result.completed.append(stage)
            stage = states.next_stage(stage, localize=self.localize)
        return result
