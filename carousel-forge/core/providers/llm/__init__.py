"""LLM 프로바이더.

기본 클라이언트는 `config/models.yaml`의 provider 설정을 따른다. 테스트는
`ScriptedLLM`을 주입해 실제 호출 없이 제약 로직만 검증한다.
"""

from __future__ import annotations

from core.config import model_routing
from core.providers.llm.base import (
    LLMClient,
    LLMError,
    LLMRefusalError,
    LLMResult,
    Profile,
)
from core.providers.llm.fake import Call, ScriptedLLM

__all__ = [
    "Call",
    "LLMClient",
    "LLMError",
    "LLMRefusalError",
    "LLMResult",
    "Profile",
    "ScriptedLLM",
    "default_client",
]


def default_client(profile: str | None = None) -> LLMClient:
    """설정에 적힌 프로바이더로 클라이언트를 만든다."""
    spec = Profile.load(profile)
    if spec.provider == "anthropic":
        from core.providers.llm.anthropic_client import AnthropicClient

        return AnthropicClient()
    raise LLMError(f"지원하지 않는 LLM 프로바이더: {spec.provider}")
