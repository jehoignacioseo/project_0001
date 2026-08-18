"""A2 TopicIntake — 문서/채팅/키워드/URL/시스템 제안을 하나의 TopicSchema로 수렴시킨다.

문서 입력의 source_fidelity 기본값은 strict다. strict일 때 원문에 없는 사실을
창작하지 않는다. 채팅 입력에서 슬롯이 비면 질문은 한 개만 되묻는다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class TopicIntake(Agent):
    name = "A2 TopicIntake"
    stage = PipelineStage.INTAKE
    milestone = "M2"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
