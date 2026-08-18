"""A8 LayoutCompositor — 배경 + CopyBlock 합성.

오토핏: 안전영역 초과 시 폰트 -5% → 자간 축소 → 줄바꿈 재계산 → 그래도 넘치면
A5에 축약 요청. 대비비가 WCAG 4.5:1 미만이면 스크림을 넣거나 배경을 재생성한다.
M1의 core/render가 실제 렌더 엔진을 이미 제공하며, 이 에이전트는 그 위에서
오토핏·대비 판정 루프를 돌린다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class LayoutCompositor(Agent):
    name = "A8 LayoutCompositor"
    stage = PipelineStage.COMPOSE
    milestone = "M4"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
