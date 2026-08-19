"""LLM 계층 — 구조화 출력만 오간다. 자유 텍스트를 긁는 경로는 없다."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from core.providers.llm import LLMError, Profile, ScriptedLLM


class Toy(BaseModel):
    value: str


def test_profiles_come_from_config():
    spec = Profile.load()
    assert spec.provider == "anthropic"
    # Opus 5에서 제거된 파라미터가 설정에 남아 있으면 런타임에 400이 난다.
    assert spec.effort in {"low", "medium", "high", "xhigh", "max"}


def test_unknown_profile_raises():
    with pytest.raises(LLMError, match="알 수 없는 LLM 프로필"):
        Profile.load("nope")


def test_config_has_no_removed_sampling_params():
    """temperature/top_p/top_k와 budget_tokens는 Opus 5에서 400이다."""
    from core.config import model_routing

    for name, block in model_routing()["llm"]["profiles"].items():
        for removed in ("temperature", "top_p", "top_k", "budget_tokens"):
            assert removed not in block, f"{name}에 제거된 파라미터 {removed}가 남아 있다"


def test_scripted_llm_returns_prepared_answers_in_order():
    llm = ScriptedLLM(responses=[Toy(value="첫째"), Toy(value="둘째")])
    first = llm.structured(system="s", user="u", output_model=Toy)
    second = llm.structured(system="s", user="u2", output_model=Toy)
    assert (first.parsed.value, second.parsed.value) == ("첫째", "둘째")
    assert llm.call_count == 2
    assert llm.calls[1].user == "u2"


def test_scripted_llm_fails_loudly_when_called_too_often():
    llm = ScriptedLLM(responses=[Toy(value="하나뿐")])
    llm.structured(system="s", user="u", output_model=Toy)
    with pytest.raises(LLMError, match="예상보다"):
        llm.structured(system="s", user="u", output_model=Toy)


def test_scripted_llm_can_react_to_the_prompt():
    """축약 재시도처럼 '앞 호출에 따라 다르게 답하는' 시나리오를 쓸 수 있다."""
    llm = ScriptedLLM(
        responses=[lambda call: Toy(value="짧게" if "축약" in call.user else "아주 길게")]
    )
    assert llm.structured(system="s", user="축약해줘", output_model=Toy).parsed.value == "짧게"
