"""폐기·재생성 루프의 예산 관리.

재시도 한도는 `config/quality_rules.yaml`에서 읽는다. 한도가 소진되면
`on_exhaust: fail_loudly` — 조용한 통과는 없다 (절대 규칙 #6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.config import quality_rules


class RetryExhausted(RuntimeError):
    """재시도 예산이 바닥났다. 애매하게 통과시키는 대신 명시적으로 실패한다."""


@dataclass
class RetryBudget:
    max_per_slide: int
    max_per_set: int
    backoff_seconds: tuple[int, ...]
    _set_attempts: int = 0
    _slide_attempts: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_config(cls) -> RetryBudget:
        rules = quality_rules()["retry"]
        return cls(
            max_per_slide=int(rules["max_attempts_per_slide"]),
            max_per_set=int(rules["max_attempts_per_set"]),
            backoff_seconds=tuple(rules.get("backoff_seconds", [0])),
        )

    def attempts_for(self, slide_index: int | None) -> int:
        return self._set_attempts if slide_index is None else self._slide_attempts.get(slide_index, 0)

    def consume(self, slide_index: int | None, reason: str) -> int:
        """재시도 1회를 소비하고 시도 회차를 돌려준다. 예산 초과면 예외."""
        self._set_attempts += 1
        if self._set_attempts > self.max_per_set:
            raise RetryExhausted(
                f"세트 재시도 한도({self.max_per_set}회) 소진. 마지막 사유: {reason}"
            )
        if slide_index is not None:
            used = self._slide_attempts.get(slide_index, 0) + 1
            self._slide_attempts[slide_index] = used
            if used > self.max_per_slide:
                raise RetryExhausted(
                    f"슬라이드 {slide_index} 재시도 한도({self.max_per_slide}회) 소진. "
                    f"마지막 사유: {reason}"
                )
            return used
        return self._set_attempts

    def backoff_for(self, attempt: int) -> int:
        if not self.backoff_seconds:
            return 0
        return self.backoff_seconds[min(attempt - 1, len(self.backoff_seconds) - 1)]
