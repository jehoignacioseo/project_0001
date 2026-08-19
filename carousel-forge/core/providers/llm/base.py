"""LLM 프로바이더 인터페이스.

에이전트는 자유 텍스트를 받지 않는다. 항상 **구조화 출력**만 주고받는다 —
`schemas/*.schema.json`에서 생성된 Pydantic 모델이 곧 계약이고, 모델이 그
형태를 지키지 못하면 파싱 단계에서 실패한다. 어중간한 텍스트를 정규식으로
긁어내는 경로는 만들지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from core.config import model_routing

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """LLM 호출이 실패했다."""


class LLMRefusalError(LLMError):
    """모델이 정책상 요청을 거절했다. 조용히 빈 결과로 넘기지 않는다."""

    def __init__(self, category: str | None, explanation: str | None) -> None:
        self.category = category
        self.explanation = explanation
        super().__init__(
            f"모델이 요청을 거절했다 (category={category}): {explanation or '설명 없음'}"
        )


@dataclass(frozen=True)
class Profile:
    """`config/models.yaml`의 llm.profiles 한 항목."""

    name: str
    provider: str
    model: str
    max_tokens: int
    effort: str | None = None

    @classmethod
    def load(cls, name: str | None = None) -> Profile:
        routing = model_routing()["llm"]
        key = name or routing["default"]
        profiles = routing["profiles"]
        if key not in profiles:
            raise LLMError(
                f"알 수 없는 LLM 프로필: {key!r}. 가능한 값: {sorted(profiles)}"
            )
        block = profiles[key]
        return cls(
            name=key,
            provider=block["provider"],
            model=block["model"],
            max_tokens=int(block["max_tokens"]),
            effort=block.get("effort"),
        )


@dataclass
class LLMResult(Generic[T]):
    """구조화 호출 결과. 사용량을 함께 들고 다녀 GenerationLog.cost에 쓴다."""

    parsed: T
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: Any = field(default=None, repr=False)


class LLMClient(ABC):
    """구조화 출력 전용 클라이언트."""

    @abstractmethod
    def structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[T],
        profile: str | None = None,
        images: list[Path] | None = None,
    ) -> LLMResult[T]:
        """`output_model` 형태의 응답을 강제해서 받아온다.

        `images`를 주면 텍스트보다 **앞에** 붙는다. 스타일 추출처럼 이미지가
        본체이고 텍스트가 지시인 경우 그 순서가 맞다.
        """
