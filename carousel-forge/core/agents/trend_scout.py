"""A3 TrendScout — 사용자가 아무것도 주지 않아도 먼저 제안한다.

score = 0.30·timeliness + 0.25·account_fit + 0.20·utility + 0.15·volume - 0.10·saturation
기존 세트와 임베딩 유사도 0.85 이상이면 제안에서 제외한다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class TrendScout(Agent):
    name = "A3 TrendScout"
    stage = PipelineStage.RESEARCH
    milestone = "M5"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
