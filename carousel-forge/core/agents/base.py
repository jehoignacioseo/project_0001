"""에이전트 공통 계약.

파이프라인 각 단계는 순수 함수적으로 설계한다: `(입력 상태, 컨텍스트) → 출력 상태`.
단계는 개별 재실행 가능해야 한다("5번 슬라이드 이미지만 다시").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from apps.api.models import PipelineStage


@dataclass
class AgentContext:
    """단계 실행에 필요한 주변 정보. 상태를 직접 변형하지 않는다."""

    account_id: str
    platform: str
    language: str
    style_dna: dict[str, Any] | None = None
    options: dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    """에이전트 한 개 = 파이프라인 한 단계.

    아직 구현되지 않은 에이전트는 `run`에서 NotImplementedError를 낸다.
    빈 결과를 돌려주고 통과한 척하지 않는다 (절대 규칙 #6).
    """

    name: str = ""
    stage: PipelineStage
    milestone: str = ""

    @abstractmethod
    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]: ...

    def _pending(self) -> NotImplementedError:
        return NotImplementedError(
            f"{self.name}은(는) {self.milestone}에서 구현된다. 현재 마일스톤 범위 밖."
        )
