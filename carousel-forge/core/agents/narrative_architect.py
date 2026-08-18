"""A4 NarrativeArchitect — 캐러셀 구조 설계.

1번 슬라이드(커버)에 전체 리소스의 40%를 투입하고 훅 후보 3개 중 가장 강한 것을
고른다. 마지막 슬라이드 직전에는 저장을 유발하는 요약본을 배치한다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class NarrativeArchitect(Agent):
    name = "A4 NarrativeArchitect"
    stage = PipelineStage.ARCHITECT
    milestone = "M2"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
