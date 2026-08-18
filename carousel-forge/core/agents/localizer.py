"""A10 Localizer — 번역이 아니라 현지화다.

중국어는 같은 의미를 한국어보다 15~30% 짧게 쓰므로 폰트 크기·줄바꿈을 재산출한다.
플랫폼이 바뀌면 캔버스 비율이 바뀌므로 레이아웃을 다시 계산한다. 해시태그는
재번역하지 않고 해당 언어권에서 실제 쓰이는 태그로 다시 조사한다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class Localizer(Agent):
    name = "A10 Localizer"
    stage = PipelineStage.LOCALIZE
    milestone = "M7"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
