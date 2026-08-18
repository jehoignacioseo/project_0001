"""A6 FactChecker — 주장 단위 병렬 검증.

false/disputed 판정이면 해당 카피를 폐기하고 A5에 수정을 요청한다.
숫자·통계·연도·인용은 출처 링크가 100% 필수이며, 출처 없는 숫자는 거부한다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class FactChecker(Agent):
    name = "A6 FactChecker"
    stage = PipelineStage.FACTCHECK
    milestone = "M5"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
