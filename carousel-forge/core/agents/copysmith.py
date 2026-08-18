"""A5 CopySmith — StyleDNA의 copy 블록을 하드 제약으로 삼아 카피를 쓴다.

글자수 상한 초과 시 자동 축약 후 재검증하고, 3회 시도로도 넘치면 레이아웃
템플릿을 더 큰 텍스트존으로 교체한다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class CopySmith(Agent):
    name = "A5 CopySmith"
    stage = PipelineStage.COPY
    milestone = "M2"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
