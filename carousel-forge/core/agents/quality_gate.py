"""A9 QualityGate — 폐기·재생성 결정권자.

config/quality_rules.yaml의 blocking 항목이 하나라도 FAIL이면 통과시키지 않는다.
판정 근거는 반드시 GenerationLog.reason에 구체적으로 남긴다. 재시도가 소진되면
조용히 통과시키지 말고 명시적으로 실패를 보고한다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class QualityGate(Agent):
    name = "A9 QualityGate"
    stage = PipelineStage.QUALITY_GATE
    milestone = "M4"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
