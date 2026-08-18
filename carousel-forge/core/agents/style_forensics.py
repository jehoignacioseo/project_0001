"""A1 StyleForensics — 벤치마크 피드에서 StyleDNA를 역설계한다.

팔레트는 눈대중이 아니라 실제 픽셀 k-means(k=6)로 뽑고, 폰트는 '유사 계열 +
대체 폰트' 쌍으로 저장하며, size_ratio는 캔버스 짧은 변 대비 비율로 남긴다.
추출 후 더미 주제로 3장을 뽑아 원본 피드와 나란히 비교하고, 사용자가
'닮았다'고 승인해야 is_active=True가 된다."""

from __future__ import annotations

from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext


class StyleForensics(Agent):
    name = "A1 StyleForensics"
    stage = PipelineStage.STYLE_RESOLVE
    milestone = "M3"

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise self._pending()
