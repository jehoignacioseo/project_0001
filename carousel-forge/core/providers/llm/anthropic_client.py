"""Claude(Anthropic) 구조화 출력 클라이언트.

`client.messages.parse(output_format=...)`로 Pydantic 모델을 강제한다. 모델이
스키마를 벗어나면 SDK가 검증에서 잡아 주므로, 우리 쪽에서 JSON을 손으로
파싱하거나 고쳐 붙이는 코드가 없다.

Opus 5 기준 주의사항:
  - temperature/top_p/top_k는 제거됐다(400). 사고량은 thinking + effort로 조절한다.
  - thinking.budget_tokens도 제거됐다. `{"type": "adaptive"}`를 쓴다.
  - stop_reason이 "refusal"로 올 수 있다. content를 읽기 전에 반드시 확인한다.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from core.config import model_routing
from core.providers.llm.base import (
    LLMClient,
    LLMError,
    LLMRefusalError,
    LLMResult,
    Profile,
)

T = TypeVar("T", bound=BaseModel)


class AnthropicClient(LLMClient):
    def __init__(self, *, api_key: str | None = None, max_retries: int = 3) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - 설치 안내
            raise LLMError("anthropic 패키지가 없다. `pip install anthropic`") from exc

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError(
                "ANTHROPIC_API_KEY가 없다. 환경변수로 넣거나 AnthropicClient(api_key=...)로 "
                "넘겨라. 키를 저장소에 커밋하지 말 것."
            )
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, max_retries=max_retries)

    def structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[T],
        profile: str | None = None,
        images: list[Path] | None = None,
    ) -> LLMResult[T]:
        spec = Profile.load(profile)

        kwargs = {
            "model": spec.model,
            "max_tokens": spec.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": _content(user, images)}],
            "output_format": output_model,
            # 구조 설계·카피 제약 검토는 사고가 필요한 작업이라 항상 켜 둔다.
            "thinking": {"type": "adaptive"},
        }
        if spec.effort:
            kwargs["output_config"] = {"effort": spec.effort}

        try:
            response = self._client.messages.parse(**kwargs)
        except self._anthropic.AuthenticationError as exc:
            raise LLMError(f"인증 실패 — API 키를 확인하라: {exc}") from exc
        except self._anthropic.RateLimitError as exc:
            raise LLMError(f"레이트 리밋 (재시도 후에도 실패): {exc}") from exc
        except self._anthropic.APIStatusError as exc:
            raise LLMError(f"API 오류 {exc.status_code}: {exc}") from exc
        except self._anthropic.APIConnectionError as exc:
            raise LLMError(f"연결 실패: {exc}") from exc

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMRefusalError(
                getattr(details, "category", None), getattr(details, "explanation", None)
            )
        if response.stop_reason == "max_tokens":
            raise LLMError(
                f"응답이 max_tokens({spec.max_tokens})에서 잘렸다. "
                f"config/models.yaml의 {spec.name}.max_tokens를 올려라."
            )

        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("구조화 출력이 비어 있다 — 모델이 계약을 지키지 못했다")

        usage = response.usage
        return LLMResult(
            parsed=parsed,
            model=response.model,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            raw=response,
        )


def fallbacks_enabled() -> bool:
    """서버측 거절 폴백 사용 여부. 실제 키로 검증한 뒤 켠다 (OPEN_QUESTIONS 16번)."""
    return bool(model_routing()["llm"].get("fallbacks_enabled", False))


_SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _content(user: str, images: list[Path] | None) -> list[dict[str, Any]] | str:
    """이미지가 있으면 이미지 → 텍스트 순으로 블록을 쌓는다."""
    if not images:
        return user

    blocks: list[dict[str, Any]] = []
    for path in images:
        media_type = mimetypes.guess_type(path.name)[0]
        if media_type not in _SUPPORTED_IMAGE_TYPES:
            raise LLMError(
                f"지원하지 않는 이미지 형식: {path.name} ({media_type}). "
                f"가능한 형식: {', '.join(sorted(_SUPPORTED_IMAGE_TYPES))}"
            )
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                },
            }
        )
    blocks.append({"type": "text", "text": user})
    return blocks
