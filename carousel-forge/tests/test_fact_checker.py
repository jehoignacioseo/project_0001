"""A6 FactChecker — 출처 없는 숫자를 거부하는 관문.

절대 규칙 #4를 강제하는 지점이다. 실제 검색은 느리고 결과가 바뀌므로, 판정
로직과 강등 규칙은 스크립트 LLM으로 결정론적으로 검증한다.
"""

from __future__ import annotations

import pytest

from apps.api.models import FactVerdict
from core.agents.base import AgentContext
from core.agents.fact_checker import (
    ClaimCheck,
    ClaimVerdict,
    FactChecker,
    FactReport,
    Source,
    UnsourcedNumber,
    find_claims_needing_sources,
    find_unsourced_numbers,
)
from core.providers.llm import ScriptedLLM
from core.providers.llm.base import SearchHit


@pytest.fixture
def ctx():
    return AgentContext(account_id="a", platform="instagram", language="ko")


# ── 출처가 필요한 표현 찾기 ─────────────────────────────────────────────

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024년에 바뀌었습니다", ["2024년"]),
        ("저장률이 3배 올랐습니다", ["3배"]),
        ("응답자 1,200명이 답했습니다", ["1,200"]),
        ("전환율이 12.5% 상승", ["12.5%"]),
        ("집중이 끊기는 건 의지 탓이 아니에요", []),
        ("오늘 하나만 골라서 해보세요", []),
    ],
)
def test_numbers_and_years_need_sources(text, expected):
    assert find_claims_needing_sources(text) == expected


def test_quotes_need_attribution():
    found = find_claims_needing_sources('연구진은 "습관이 의지를 이긴다"고 말합니다')
    assert found == ["습관이 의지를 이긴다"]


def test_plain_copy_needs_nothing():
    """숫자가 없는 카피까지 출처를 요구하면 아무것도 못 쓴다."""
    assert find_claims_needing_sources("책상을 바꾸면 집중이 바뀝니다") == []


# ── 카피 대조 ───────────────────────────────────────────────────────────

def _copy(text: str, role: str = "body"):
    return {
        "slides": [
            {
                "index": 1,
                "role": "point",
                "copy_blocks": [{"id": "s01_body", "role": role, "text": text}],
            }
        ]
    }


def test_a_number_backed_by_a_verified_claim_passes():
    checks = [
        ClaimCheck(
            claim="인스타그램 캐러셀은 최대 20장이다",
            verdict=FactVerdict.VERIFIED,
            reasoning="공식 문서에 20개로 명시돼 있다",
            sources=[Source("Instagram Help", "https://help.instagram.com/269314186824048/")],
        )
    ]
    assert find_unsourced_numbers(_copy("한 게시물에 20장까지 올릴 수 있어요"), checks) == []


def test_a_number_with_no_verified_claim_is_rejected():
    """절대 규칙 #4 — 출처 없는 숫자는 파이프라인이 거부한다."""
    unsourced = find_unsourced_numbers(_copy("저장률이 3배 오릅니다"), checks=[])
    assert len(unsourced) == 1
    assert unsourced[0].found == "3배"
    assert unsourced[0].block_id == "s01_body"


def test_an_unverified_claim_does_not_cover_its_number():
    """unverified는 근거가 아니다. 그 숫자는 여전히 출처가 없다."""
    checks = [
        ClaimCheck(
            claim="저장률이 3배 오른다",
            verdict=FactVerdict.UNVERIFIED,
            reasoning="근거를 찾지 못했다",
        )
    ]
    assert len(find_unsourced_numbers(_copy("저장률이 3배 오릅니다"), checks)) == 1


def test_slide_numbers_are_not_treated_as_claims():
    """뱃지의 '01'은 사실 주장이 아니라 구조 요소다."""
    assert find_unsourced_numbers(_copy("03", role="badge"), checks=[]) == []


# ── 판정 강등 ───────────────────────────────────────────────────────────

def _verdict(**kw):
    base = dict(verdict="verified", reasoning="근거가 충분하다", source_urls=[])
    return ClaimVerdict(**{**base, **kw})


def test_verified_without_sources_is_demoted(ctx):
    """출처 없이 verified는 성립하지 않는다."""
    llm = ScriptedLLM(responses=[_verdict(source_urls=[])])
    checks = FactChecker(llm=llm).verify_claims(["어떤 주장"], ctx)

    assert checks[0].verdict is FactVerdict.UNVERIFIED
    assert "자동 강등" in checks[0].reasoning


def test_verified_survives_when_search_actually_opened_the_source(ctx):
    llm = ScriptedLLM(
        responses=[_verdict(source_urls=["https://help.instagram.com/269314186824048/"])]
    )
    llm.search_hits = [SearchHit(title="Instagram Help", url="https://help.instagram.com/269314186824048/")]
    checks = FactChecker(llm=llm).verify_claims(["어떤 주장"], ctx)

    assert checks[0].verdict is FactVerdict.VERIFIED
    assert checks[0].sources[0].domain == "help.instagram.com"
    assert checks[0].unverified_urls == []


def test_urls_the_search_never_opened_are_not_counted_as_sources(ctx):
    """모델이 그럴듯하게 지어낸 URL을 출처로 통과시키지 않는다."""
    llm = ScriptedLLM(
        responses=[_verdict(source_urls=["https://example.com/made-up-study"])]
    )
    llm.search_hits = [SearchHit(title="다른 페이지", url="https://help.instagram.com/1/")]
    checks = FactChecker(llm=llm).verify_claims(["어떤 주장"], ctx)

    assert checks[0].unverified_urls == ["https://example.com/made-up-study"]
    assert checks[0].verdict is FactVerdict.UNVERIFIED  # 출처가 남지 않아 강등된다


def test_a_different_path_on_an_opened_domain_counts(ctx):
    """검색 결과에서 본 사이트의 다른 경로를 적는 것은 흔하고, 지어낸 것과 다르다."""
    llm = ScriptedLLM(
        responses=[_verdict(source_urls=["https://help.instagram.com/269314186824048/"])]
    )
    llm.search_hits = [SearchHit(title="Help", url="https://help.instagram.com/other")]
    checks = FactChecker(llm=llm).verify_claims(["어떤 주장"], ctx)

    assert checks[0].verdict is FactVerdict.VERIFIED
    assert checks[0].unverified_urls == []


def test_an_unknown_verdict_is_not_read_as_pass(ctx):
    llm = ScriptedLLM(responses=[_verdict(verdict="probably fine", source_urls=[])])
    checks = FactChecker(llm=llm).verify_claims(["어떤 주장"], ctx)
    assert checks[0].verdict is FactVerdict.UNVERIFIED


def test_each_claim_is_checked_independently(ctx):
    """한 번에 몰아 물으면 앞 판정에 뒤 판정을 맞춘다."""
    llm = ScriptedLLM(responses=[_verdict(), _verdict(), _verdict()])
    FactChecker(llm=llm).verify_claims(["주장 1", "주장 2", "주장 3"], ctx)

    assert llm.call_count == 3
    users = [c.user for c in llm.calls]
    assert "주장 1" in users[0] and "주장 2" not in users[0]


def test_verification_asks_for_search(ctx):
    """검색 없이 기억으로 판정하면 팩트체크가 아니다."""
    llm = ScriptedLLM(responses=[_verdict()])
    FactChecker(llm=llm).verify_claims(["어떤 주장"], ctx)
    assert llm.calls[0].search is True


def test_a_failed_call_does_not_become_verified(ctx):
    from core.providers.llm import LLMError

    class Failing(ScriptedLLM):
        def structured(self, **kwargs):
            raise LLMError("레이트 리밋")

    checks = FactChecker(llm=Failing(responses=[])).verify_claims(["어떤 주장"], ctx)
    assert checks[0].verdict is FactVerdict.UNVERIFIED
    assert "검증을 수행하지 못했다" in checks[0].reasoning


# ── 보고서 ──────────────────────────────────────────────────────────────

def test_false_and_disputed_block_publication():
    for verdict in (FactVerdict.FALSE, FactVerdict.DISPUTED):
        report = FactReport(
            claims=[ClaimCheck("주장", verdict, "출처가 반박한다")]
        )
        assert not report.passed
        assert report.blocking


def test_unverified_warns_but_does_not_block():
    """unverified는 단정형을 완화하거나 삭제하면 된다 — 폐기 사유는 아니다."""
    report = FactReport(claims=[ClaimCheck("주장", FactVerdict.UNVERIFIED, "근거 없음")])
    assert report.passed
    assert len(report.needs_softening) == 1


def test_unsourced_numbers_block_publication():
    report = FactReport(
        claims=[],
        unsourced=[UnsourcedNumber(1, "s01_body", "3배 오릅니다", "3배")],
    )
    assert not report.passed


def test_markdown_report_lists_every_source():
    report = FactReport(
        claims=[
            ClaimCheck(
                "인스타그램 캐러셀은 최대 20장이다",
                FactVerdict.VERIFIED,
                "공식 문서 확인",
                sources=[Source("Instagram Help", "https://help.instagram.com/1/")],
            )
        ]
    )
    markdown = report.markdown()
    assert "https://help.instagram.com/1/" in markdown
    assert "✅" in markdown


def test_markdown_marks_claims_with_no_sources():
    report = FactReport(claims=[ClaimCheck("주장", FactVerdict.UNVERIFIED, "근거 없음")])
    assert "출처: **없음**" in report.markdown()


# ── 품질 게이트 연결 ────────────────────────────────────────────────────

def _gate():
    from core.agents.quality_gate import QualityGate

    return QualityGate(use_vision=False)


def test_the_gate_blocks_on_false_claims():
    from core.agents.base import AgentContext

    report = FactReport(
        claims=[ClaimCheck("틀린 주장", FactVerdict.FALSE, "출처가 반박한다")]
    ).as_dict()
    judgements = _gate()._rules(
        report, None, AgentContext("a", "instagram", "ko"), {"factcheck_false"}, set()
    )
    failed = next(j for j in judgements if j.rule_id == "factcheck_false")
    assert not failed.passed
    assert "false" in failed.reason


def test_the_gate_blocks_on_unsourced_numbers():
    """절대 규칙 #4가 게이트에 실제로 연결돼 있는가."""
    from core.agents.base import AgentContext

    report = FactReport(
        claims=[],
        unsourced=[UnsourcedNumber(2, "s02_body", "3배 오릅니다", "3배")],
    ).as_dict()
    judgements = _gate()._rules(
        report, None, AgentContext("a", "instagram", "ko"), {"unsourced_claim"}, set()
    )
    failed = next(j for j in judgements if j.rule_id == "unsourced_claim")
    assert not failed.passed
    assert "3배" in failed.reason
    assert failed.slide_index == 2


def test_a_clean_report_passes_the_gate():
    from core.agents.base import AgentContext

    report = FactReport(
        claims=[
            ClaimCheck(
                "맞는 주장", FactVerdict.VERIFIED, "공식 문서 확인",
                sources=[Source("Help", "https://help.instagram.com/1/")],
            )
        ]
    ).as_dict()
    judgements = _gate()._rules(
        report, None, AgentContext("a", "instagram", "ko"),
        {"factcheck_false", "unsourced_claim"}, set(),
    )
    assert all(j.passed for j in judgements)


def test_a_missing_report_is_reported_not_assumed_clean():
    """검증을 안 했으면 안 했다고 남긴다."""
    from core.agents.base import AgentContext

    judgements = _gate()._rules(
        None, None, AgentContext("a", "instagram", "ko"), {"factcheck_false"}, set()
    )
    factcheck = next(j for j in judgements if j.rule_id == "factcheck_false")
    assert factcheck.severity == "warning"
    assert "검증되지 않은" in factcheck.reason
