"""M2 에이전트 — 모델 없이 제약·구조 로직만 검증한다.

실제 카피 품질은 사람이 보는 것이고, 여기서 고정하는 것은 **제약이 강제되는가**다.
`ScriptedLLM`이 정해진 답을 돌려주므로 축약 루프를 정확히 몇 번 도는지까지 셀 수 있다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.api.schemas.generated.copy import Caption
from core.agents import NarrativeArchitect, TopicIntake, check_outline
from core.agents.base import AgentContext
from core.agents.copysmith import (
    MAX_SHRINK_ATTEMPTS,
    CaptionDraft,
    CopyBlockDraft,
    CopyError,
    CopySmith,
    SlideCopyDraft,
    SlideCopySet,
)
from core.agents.narrative_architect import _role_sequence, resolve_slide_count
from core.agents.topic_intake import read_document
from core.config import platform_spec
from core.providers.llm import ScriptedLLM

DNA = json.loads((Path(__file__).parent / "fixtures/style_dna_demo.json").read_text(encoding="utf-8"))


@pytest.fixture
def ctx():
    return AgentContext(account_id="a", platform="instagram", language="ko", style_dna=DNA)


# ── A4 NarrativeArchitect ───────────────────────────────────────────────

def test_slide_count_follows_the_style_range():
    spec = platform_spec("instagram")
    lo, hi = DNA["structure"]["slide_count_range"]
    for points in range(0, 10):
        count = resolve_slide_count(DNA, {"supporting_points": ["p"] * points}, spec)
        assert lo <= count <= hi, f"{points}개 포인트에서 {count}장이 나왔다"


def test_slide_count_never_exceeds_the_platform_limit():
    spec = platform_spec("instagram")
    dna = json.loads(json.dumps(DNA))
    dna["structure"]["slide_count_range"] = [5, 50]
    count = resolve_slide_count(dna, {"supporting_points": ["p"] * 40}, spec)
    assert count <= spec.max_slides


def test_role_sequence_keeps_the_skeleton():
    """커버는 hook, 마지막은 cta, 그 직전은 저장 유발 요약이다."""
    for count in range(5, 11):
        roles = _role_sequence(DNA, count)
        assert len(roles) == count
        assert roles[0] == "hook"
        assert roles[-1] == "cta"
        assert roles[-2] == "summary"


def test_outline_check_rejects_text_in_the_visual_brief():
    """배경 프롬프트에 글자 요구가 섞이면 잡는다 (절대 규칙 #5)."""
    outline = {
        "slides": [
            {"index": 1, "role": "hook", "visual_brief": "a desk with the words FOCUS painted"},
            {"index": 2, "role": "cta", "visual_brief": "quiet morning light"},
        ],
        "hook_candidates": [{}, {}, {}],
    }
    problems = check_outline(outline, platform_spec("instagram"))
    assert any("글자를 넣으라는 요구" in p.message for p in problems)


def test_outline_check_flags_a_missing_summary():
    outline = {
        "slides": [
            {"index": i, "role": r, "visual_brief": "x"}
            for i, r in enumerate(["hook", "point", "point", "point", "cta"], start=1)
        ],
        "hook_candidates": [{}, {}, {}],
    }
    problems = check_outline(outline, platform_spec("instagram"))
    assert any("요약(summary) 슬라이드가 없다" in p.message for p in problems)


# ── A5 CopySmith ────────────────────────────────────────────────────────

def _outline(count: int = 3) -> dict:
    roles = ["hook"] + ["point"] * (count - 2) + ["cta"]
    return {
        "title_working": "제목",
        "slide_count": count,
        "hook_candidates": [{"text": "훅", "rationale": "r", "strength_score": 0.9}] * 3,
        "chosen_hook_index": 0,
        "slides": [
            {
                "index": i,
                "role": role,
                "single_message": f"메시지 {i}",
                "visual_brief": "조용한 책상",
                "layout_template": {"hook": "hook", "cta": "cta"}.get(role, "point"),
            }
            for i, role in enumerate(roles, start=1)
        ],
    }


def _slides(headline: str, count: int = 3) -> SlideCopySet:
    return SlideCopySet(
        slides=[
            SlideCopyDraft(index=i, blocks=[CopyBlockDraft(role="headline", text=headline)])
            for i in range(1, count + 1)
        ]
    )


def _caption() -> CaptionDraft:
    return CaptionDraft(
        caption=Caption(hook_line="짧은 훅", body="본문" * 100, cta="저장해두세요"),
        hashtags=[f"#t{i}" for i in range(12)],
    )


def test_copy_within_limits_needs_no_retry(ctx):
    llm = ScriptedLLM(responses=[_slides("딱 맞는 헤드라인"), _caption()])
    result = CopySmith(llm=llm).write(_outline(), ctx)
    assert result.attempts == 1
    assert llm.call_count == 2      # 초안 + 캡션. 축약 호출 없음
    assert not result.template_swaps


def test_over_limit_copy_triggers_a_shrink_round(ctx):
    """상한을 넘으면 축약을 요청하고, 맞으면 거기서 멈춘다."""
    too_long = "가" * 40      # headline 상한 24자
    llm = ScriptedLLM(responses=[_slides(too_long), _slides("줄인 헤드라인"), _caption()])
    result = CopySmith(llm=llm).write(_outline(), ctx)
    assert result.attempts == 2
    assert "축약" in llm.calls[1].user
    assert all(
        len(b["text"]) <= b["max_chars"]
        for s in result.slides for b in s["copy_blocks"]
    )


def test_the_shrink_prompt_names_the_actual_violation(ctx):
    """'뭔가 잘못됐다'가 아니라 어떤 블록이 몇 자 넘었는지 알려 준다."""
    llm = ScriptedLLM(responses=[_slides("가" * 40), _slides("짧게"), _caption()])
    CopySmith(llm=llm).write(_outline(), ctx)
    assert "s01_headline" in llm.calls[1].user
    assert "24자" in llm.calls[1].user


def test_exhausted_retries_fail_loudly_rather_than_pass(ctx):
    """축약도 템플릿 교체도 안 되면 조용히 통과시키지 않는다 (절대 규칙 #6)."""
    forever = "가" * 40
    llm = ScriptedLLM(responses=[_slides(forever)] * (MAX_SHRINK_ATTEMPTS + 3))
    with pytest.raises(CopyError) as exc:
        CopySmith(llm=llm).write(_outline(), ctx)
    assert "s01_headline" in str(exc.value)


def test_forbidden_words_also_trigger_the_shrink_loop(ctx):
    llm = ScriptedLLM(responses=[_slides("이건 대박이에요"), _slides("이건 좋아요"), _caption()])
    result = CopySmith(llm=llm).write(_outline(), ctx)
    assert result.attempts == 2
    assert "금지어" in llm.calls[1].user


def test_blocks_outside_the_template_are_rejected(ctx):
    """hook 템플릿에 body 블록을 넣으면 렌더에서 사라지므로 미리 잡는다."""
    bad = SlideCopySet(
        slides=[
            SlideCopyDraft(index=1, blocks=[CopyBlockDraft(role="body", text="본문")]),
            SlideCopyDraft(index=2, blocks=[CopyBlockDraft(role="headline", text="좋아요")]),
            SlideCopyDraft(index=3, blocks=[CopyBlockDraft(role="headline", text="좋아요")]),
        ]
    )
    good = _slides("좋아요")
    llm = ScriptedLLM(responses=[bad, good, _caption()])
    result = CopySmith(llm=llm).write(_outline(), ctx)
    assert result.attempts == 2
    assert "템플릿에 없는 블록" in llm.calls[1].user


def test_caption_hook_over_the_fold_is_rejected(ctx):
    bad_caption = CaptionDraft(
        caption=Caption(hook_line="가" * 200, body="본문" * 100, cta="저장"),
        hashtags=[f"#t{i}" for i in range(12)],
    )
    llm = ScriptedLLM(responses=[_slides("좋아요"), bad_caption])
    with pytest.raises(CopyError, match="접히므로 훅이 잘린다"):
        CopySmith(llm=llm).write(_outline(), ctx)


def test_copysmith_requires_style_dna():
    bare = AgentContext(account_id="a", platform="instagram", language="ko")
    with pytest.raises(CopyError, match="하드 제약"):
        CopySmith(llm=ScriptedLLM(responses=[])).write(_outline(), bare)


# ── A2 TopicIntake ──────────────────────────────────────────────────────

def test_document_reader_rejects_unknown_formats(tmp_path):
    path = tmp_path / "note.rtf"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="지원하지 않는 문서 형식"):
        read_document(path)


def test_document_reader_handles_markdown(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("# 제목\n본문입니다", encoding="utf-8")
    assert "본문입니다" in read_document(path)


def test_missing_document_is_not_silently_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_document(tmp_path / "없는파일.md")


def test_url_and_proposed_inputs_name_their_milestone(ctx):
    with pytest.raises(NotImplementedError, match="M5"):
        TopicIntake(llm=ScriptedLLM(responses=[])).run(
            {"input_type": "proposed", "payload": None}, ctx
        )


def test_architect_requires_style_dna():
    from core.agents.narrative_architect import OutlineError

    bare = AgentContext(account_id="a", platform="instagram", language="ko")
    with pytest.raises(OutlineError, match="StyleDNA 없이는"):
        NarrativeArchitect(llm=ScriptedLLM(responses=[])).run({"topic": {}}, bare)
