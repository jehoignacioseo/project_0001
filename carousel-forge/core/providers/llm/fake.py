"""테스트용 가짜 LLM.

에이전트의 **제약 강제 로직**(글자수 상한, 금지어, 이모지 밀도, 축약 재시도)은
모델 없이도 전부 검증할 수 있어야 한다. 그 검증을 실제 API 호출에 묶어 두면
테스트가 느려지고 비결정적이 된다.

`ScriptedLLM`은 미리 정해 둔 응답을 순서대로 돌려준다. 응답이 떨어지면 조용히
반복하지 않고 실패한다 — 예상보다 많이 호출됐다는 사실 자체가 버그이기 때문이다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from core.providers.llm.base import LLMClient, LLMError, LLMResult

T = TypeVar("T", bound=BaseModel)


@dataclass
class Call:
    """기록된 호출 한 건. 프롬프트에 제약이 실렸는지 검사할 때 쓴다."""

    system: str
    user: str
    output_model: type[BaseModel]
    profile: str | None
    images: tuple[Path, ...] = ()


@dataclass
class ScriptedLLM(LLMClient):
    """정해진 순서대로 응답을 돌려주는 가짜 클라이언트.

    각 항목은 완성된 모델 인스턴스이거나, `(call) -> 모델` 콜러블이다.
    콜러블을 쓰면 "첫 호출은 글자수를 넘기고, 축약 요청에는 짧게 답한다" 같은
    시나리오를 그대로 쓸 수 있다.
    """

    responses: list[Any]
    calls: list[Call] = field(default_factory=list)
    _cursor: int = 0

    def structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[T],
        profile: str | None = None,
        images: list[Path] | None = None,
    ) -> LLMResult[T]:
        call = Call(
            system=system,
            user=user,
            output_model=output_model,
            profile=profile,
            images=tuple(images or ()),
        )
        self.calls.append(call)

        if self._cursor >= len(self.responses):
            raise LLMError(
                f"ScriptedLLM에 준비된 응답이 {len(self.responses)}개인데 "
                f"{len(self.calls)}번째 호출이 들어왔다. 에이전트가 예상보다 "
                "많이 호출하고 있다."
            )
        item = self.responses[self._cursor]
        self._cursor += 1

        value = item(call) if isinstance(item, Callable) else item
        if not isinstance(value, output_model):
            raise LLMError(
                f"준비된 응답이 {output_model.__name__}이 아니라 {type(value).__name__}이다"
            )
        return LLMResult(parsed=value, model="scripted", input_tokens=0, output_tokens=0)

    @property
    def call_count(self) -> int:
        return len(self.calls)
