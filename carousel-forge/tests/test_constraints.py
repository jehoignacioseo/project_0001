"""StyleDNA 제약은 하드 제약이다 (절대 규칙 #8).

제약 판정은 순수 함수라 모델 없이 전부 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agents.constraints import (
    CaptionConstraints,
    CopyConstraints,
    blocking,
    emoji_count,
    visible_length,
)
from core.config import platform_spec

DNA = json.loads((Path(__file__).parent / "fixtures/style_dna_demo.json").read_text(encoding="utf-8"))


@pytest.fixture
def constraints():
    return CopyConstraints.from_dna(DNA, platform_spec("instagram"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [("글자만", 0), ("반짝✨", 1), ("✨🔖", 2), ("가족👨‍👩‍👧이야", 1), ("체크✔️", 1)],
)
def test_emoji_count(text, expected):
    assert emoji_count(text) == expected


def test_visible_length_ignores_line_breaks():
    """줄바꿈은 글자수에 세지 않는다 — 사람이 화면에서 세는 감각을 따른다."""
    assert visible_length("집중이\n끊긴다") == 6
    assert visible_length("가나다") == 3


def test_headline_over_limit_is_blocking(constraints):
    long = "가" * (constraints.headline_char_limit + 3)
    problems = constraints.check_text(long, field_name="s01_headline", role="headline")
    assert any("3자 넘는다" in p.message for p in blocking(problems))


def test_line_breaks_do_not_count_toward_the_limit(constraints):
    text = "\n".join(["가" * (constraints.headline_char_limit // 2)] * 2)
    assert constraints.check_text(text, field_name="s01_headline", role="headline") == []


def test_forbidden_words_are_rejected(constraints):
    problems = constraints.check_text("이거 진짜 대박", field_name="s01_headline", role="headline")
    assert any("금지어" in p.message for p in problems)


def test_zero_emoji_density_means_none_at_all(constraints):
    assert constraints.emoji_density == 0.0
    problems = constraints.check_text("좋아요 ✨", field_name="s02_body", role="body")
    assert any("이모지를 쓰지 않는다" in p.message for p in problems)


def test_emoji_palette_is_enforced_when_emoji_are_allowed():
    dna = json.loads(json.dumps(DNA))
    dna["copy"]["emoji_density"] = 0.2
    dna["copy"]["emoji_palette"] = ["✨"]
    c = CopyConstraints.from_dna(dna, platform_spec("instagram"))
    assert c.check_text("좋아요 ✨", field_name="s02_body", role="body") == []
    problems = c.check_text("좋아요 🔥", field_name="s02_body", role="body")
    assert any("팔레트 밖 이모지" in p.message for p in problems)


def test_role_specific_limits(constraints):
    """라벨류는 헤드라인보다 짧게, 본문은 본문 상한을 쓴다."""
    assert constraints.limit_for("headline") == constraints.headline_char_limit
    assert constraints.limit_for("body") == constraints.body_char_limit
    assert constraints.limit_for("eyebrow") < constraints.headline_char_limit


def test_xiaohongshu_cover_title_limit_is_picked_up():
    c = CopyConstraints.from_dna(DNA, platform_spec("xiaohongshu"))
    assert c.cover_title_limit == 20
    assert CopyConstraints.from_dna(DNA, platform_spec("instagram")).cover_title_limit is None


# ── 캡션 ────────────────────────────────────────────────────────────────

@pytest.fixture
def caption_rules():
    return CaptionConstraints.from_dna(DNA, platform_spec("instagram"))


def test_hook_line_must_fit_before_the_fold(caption_rules):
    long_hook = "가" * 130
    problems = caption_rules.check(long_hook, "본문", "저장", ["#a"] * 12)
    assert any("접히므로 훅이 잘린다" in p.message for p in blocking(problems))


def test_duplicate_hashtags_are_blocking(caption_rules):
    tags = ["#러닝"] * 2 + [f"#t{i}" for i in range(10)]
    problems = caption_rules.check("훅", "본문", "저장", tags)
    assert any("중복된 태그" in p.message for p in blocking(problems))


def test_hashtag_count_mismatch_is_only_a_warning(caption_rules):
    problems = caption_rules.check("훅", "가" * 300, "저장", ["#a", "#b"])
    counts = [p for p in problems if "이 계정의 전략은" in p.message]
    assert counts and all(p.severity == "warning" for p in counts)


def test_caption_over_platform_max_is_blocking(caption_rules):
    problems = caption_rules.check("훅", "가" * 2300, "저장", [])
    assert any("플랫폼 상한" in p.message for p in blocking(problems))
