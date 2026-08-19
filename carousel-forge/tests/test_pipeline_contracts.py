"""파이프라인 계약 — 미구현을 조용히 통과시키지 않는다 (절대 규칙 #6)."""

from __future__ import annotations

import pytest

from apps.api.models import PipelineStage
from core.agents import CopySmith, QualityGate
from core.agents.base import AgentContext
from core.config import quality_rules
from core.pipeline import Orchestrator, RetryBudget, RetryExhausted, next_stage, rewind_for
from core.pipeline.states import REWIND_TARGET, SEQUENCE
from core.providers.image import HiggsfieldProvider, ImageRequest, TextInPromptError


def test_every_blocking_rule_has_a_rewind_target():
    """폐기 사유가 늘면 되감기 지점도 같이 정의돼야 한다."""
    blocking = {r["id"] for r in quality_rules()["blocking"]}
    # 비전 판정 규칙은 전부 VISUAL_GEN으로 되감긴다.
    missing = blocking - set(REWIND_TARGET)
    assert not missing, f"되감기 지점이 없는 폐기 사유: {sorted(missing)}"


def test_rewind_for_unknown_rule_raises():
    with pytest.raises(KeyError, match="되감기 지점이 정의되지 않은"):
        rewind_for("made_up_rule")


def test_localize_is_skipped_unless_requested():
    assert next_stage(PipelineStage.QUALITY_GATE) is PipelineStage.EXPORT
    assert next_stage(PipelineStage.QUALITY_GATE, localize=True) is PipelineStage.LOCALIZE
    assert next_stage(SEQUENCE[-1]) is None


def test_unimplemented_agents_raise_instead_of_returning_empty():
    """M4까지 붙은 지금 남은 미구현은 A3·A6·A10이다."""
    from core.agents import FactChecker, Localizer, TrendScout

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    for agent in (TrendScout(), FactChecker(), Localizer()):
        with pytest.raises(NotImplementedError):
            agent.run({}, ctx)


def test_a8_refuses_the_state_dict_interface():
    """A8은 RenderSet을 받는다. 상태 딕셔너리로 부르면 조용히 아무것도 안 하지 않는다."""
    from core.agents import LayoutCompositor

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    with pytest.raises(NotImplementedError, match="compose"):
        LayoutCompositor().run({}, ctx)


def test_orchestrator_stops_at_the_first_unimplemented_stage():
    """M3까지 붙은 지금, 상태 머신은 A3 TrendScout(M5) 자리에서 멈춘다.

    파이프라인 순서와 마일스톤 순서가 다르기 때문에 전 구간은 M5까지 가야 열린다.
    그 전까지 각 마일스톤 산출물은 데모 스크립트가 에이전트를 직접 이어 확인한다.
    """
    result = Orchestrator(AgentContext("a", "instagram", "ko")).run(
        {}, start=PipelineStage.RESEARCH
    )
    assert result.stopped_at is PipelineStage.RESEARCH
    assert "M5" in result.error


def test_retry_budget_fails_loudly_when_exhausted():
    budget = RetryBudget(max_per_slide=2, max_per_set=10, backoff_seconds=(0, 2))
    budget.consume(3, "첫 폐기")
    budget.consume(3, "두 번째 폐기")
    with pytest.raises(RetryExhausted, match="슬라이드 3"):
        budget.consume(3, "세 번째 폐기")


def test_set_level_budget_is_enforced():
    budget = RetryBudget(max_per_slide=99, max_per_set=2, backoff_seconds=(0,))
    budget.consume(1, "a")
    budget.consume(2, "b")
    with pytest.raises(RetryExhausted, match="세트 재시도 한도"):
        budget.consume(3, "c")


def test_image_prompt_may_not_ask_for_text():
    """글자는 항상 렌더 레이어에서 처리한다 (절대 규칙 #5)."""
    with pytest.raises(TextInPromptError):
        HiggsfieldProvider().generate(
            ImageRequest(prompt="a desk with the words FOCUS on the wall", width=1080, height=1350)
        )


def test_negative_prompt_always_includes_ai_tells():
    request = ImageRequest(prompt="a quiet desk at dusk", width=1080, height=1350)
    negative = request.full_negative()
    for must in ("text", "watermark", "plastic smooth skin", "oversaturated"):
        assert must in negative
