"""A7 ArtDirector — 텍스트가 없는 배경만 생성한다.

프롬프트에 텍스트 렌더링을 요청하지 않는다(AI 텍스트 오류의 근원). 텍스트가
얹힐 영역은 저정보 영역으로 확보하도록 명시하고, 슬라이드 간 팔레트·조명·
렌즈감·그레인을 잠근다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class ArtDirector(Agent):
    name = "A7 ArtDirector"
    stage = PipelineStage.VISUAL_GEN
    milestone = "M4"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
