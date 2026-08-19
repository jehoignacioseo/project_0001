"""A10 Localizer — 번역이 아니라 현지화인지, 그리고 제약이 실제로 강제되는지.

실제 LLM 호출은 느리고 비결정적이므로 판정 로직만 스크립트 LLM으로 검증한다.
여기서 확인하는 것은 "모델이 좋은 중국어를 쓰는가"가 아니라 **모델이 무엇을 해도
파이프라인이 규격 밖 결과를 통과시키지 않는가**다.
"""

from __future__ import annotations

import pytest

from apps.api.models import VariantType
from core.agents.base import AgentContext
from core.agents.localizer import (
    HashtagSet,
    LocalizationError,
    LocalizedBlock,
    LocalizedCopy,
    LocalizedSlide,
    Localizer,
    ResearchedTag,
    cover_title_report,
    retarget_dna,
)
from core.config import localization_pair, platform_spec
from core.platform.base import adapter_for
from core.providers.llm import ScriptedLLM
from core.providers.llm.base import SearchHit
from core.render.capacity import RoleCapacity
from tests.fixtures.demo_set import demo_copy, demo_style_dna

TARGET = {"target_platform": "xiaohongshu", "target_language": "zh"}


@pytest.fixture
def dna():
    return demo_style_dna()


@pytest.fixture
def copy():
    return demo_copy()


@pytest.fixture
def ctx(dna):
    return AgentContext(
        account_id="deskreset", platform="instagram", language="ko", style_dna=dna
    )


# ── StyleDNA 재조준 ─────────────────────────────────────────────────────

def test_target_font_comes_from_the_dna_not_from_code(dna):
    """폰트는 설정이 아니라 계정 자산이다 (절대 규칙 #8)."""
    out, _ = retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")
    expected = dna["visual"]["typography"]["chinese_font"]
    for role in ("headline", "body", "accent"):
        assert out["visual"]["typography"][role]["family"] == expected


def test_a_missing_target_font_fails_instead_of_falling_back(dna):
    dna["visual"]["typography"]["chinese_font"] = ""
    with pytest.raises(LocalizationError, match="폰트가 없다"):
        retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")


def test_the_target_font_is_first_not_a_fallback(dna):
    """Figma에는 글리프 단위 폴백이 없다. 첫 폰트가 한자를 못 그리면 두부가 된다."""
    out, _ = retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")
    fallback = out["visual"]["typography"]["headline"]["fallback"]
    assert dna["visual"]["typography"]["korean_font"] not in fallback


def test_char_limits_shrink_by_the_configured_language_ratio(dna):
    out, _ = retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")
    ratio = localization_pair("ko", "zh").hard_ratio
    assert out["copy"]["headline_char_limit"] == int(24 * ratio)
    assert out["copy"]["body_char_limit_per_slide"] == int(80 * ratio)


def test_measured_capacity_wins_when_it_is_tighter(dna):
    """문체가 허용해도 자리가 없으면 넘친다. 실측이 상한을 내린다."""
    capacity = {"headline": RoleCapacity("headline", chars_per_line=3, max_lines=2, line_width_px=888)}
    out, warnings = retarget_dna(
        dna, target_language="zh", target_platform="xiaohongshu", capacity=capacity
    )
    assert out["copy"]["headline_char_limit"] == 6
    assert any("실측 수용량" in w.message for w in warnings)


def test_roomy_capacity_does_not_loosen_the_style_limit(dna):
    """자리가 남는다고 계정 문체보다 길게 쓰게 두지 않는다."""
    capacity = {"headline": RoleCapacity("headline", chars_per_line=40, max_lines=4, line_width_px=888)}
    out, _ = retarget_dna(
        dna, target_language="zh", target_platform="xiaohongshu", capacity=capacity
    )
    assert out["copy"]["headline_char_limit"] == int(24 * localization_pair("ko", "zh").hard_ratio)


def test_identity_and_palette_survive_the_language_change(dna):
    """언어가 바뀌어도 그 계정이 그 계정이어야 한다."""
    out, _ = retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")
    assert out["visual"]["palette"] == dna["visual"]["palette"]
    assert out["visual"]["layout"] == dna["visual"]["layout"]
    assert out["identity"] == dna["identity"]


def test_hashtag_count_is_clamped_to_the_target_platform(dna):
    out, warnings = retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")
    assert out["caption"]["hashtag_strategy"]["count"] == platform_spec("xiaohongshu").hashtag_max
    assert any("태그 전략" in w.message for w in warnings)


def test_an_emoji_culture_clash_is_reported_not_silently_resolved(dna):
    """샤오홍슈는 이모지를 많이 쓰지만 DNA는 하드 제약이다. 사람이 알아야 한다."""
    _, warnings = retarget_dna(dna, target_language="zh", target_platform="xiaohongshu")
    assert any(w.field == "copy.emoji_density" for w in warnings)


def test_an_undefined_language_pair_is_not_guessed(dna):
    from core.config import ConfigError

    with pytest.raises(ConfigError, match="언어 쌍"):
        retarget_dna(dna, target_language="en", target_platform="instagram")


# ── 카피 현지화 ─────────────────────────────────────────────────────────

def _localized(copy, *, texts=None, caption=None, register="口语体", notes=()):
    """원본 블록 id를 그대로 쓴 현지화 결과 한 건."""
    slides = []
    for slide in copy["slides"]:
        blocks = []
        for block in slide["copy_blocks"]:
            text = (texts or {}).get(block["id"], "专注")
            blocks.append(LocalizedBlock(id=block["id"], text=text))
        slides.append(LocalizedSlide(index=slide["index"], blocks=blocks))
    return LocalizedCopy(
        slides=slides,
        caption=caption
        or {
            "hook_line": "换个桌面，专注力就回来了。",
            "body": "不是让你买新设备。\n是把已有的东西换个位置。" * 6,
            "cta": "收藏起来，晚上就能做完。",
        },
        target_register=register,
        signature_phrases=["从今天起"],
        notes=list(notes),
    )


def _tags(n=10):
    return HashtagSet(
        tags=[
            ResearchedTag(tag=f"#桌面改造{i}", kind="niche", evidence="샤오홍슈 검색 결과 상위")
            for i in range(n)
        ]
    )


def _llm(*responses, hits=True):
    llm = ScriptedLLM(responses=list(responses))
    if hits:
        llm.search_hits = [SearchHit(title="小红书 话题", url="https://www.xiaohongshu.com/search")]
    return llm


def test_a_clean_localization_links_back_to_the_original(copy, ctx):
    llm = _llm(_localized(copy), _tags())
    result = Localizer(llm=llm).localize(
        copy, ctx, parent_set_id="set_ko_0001", **TARGET
    )

    assert result.variant_type is VariantType.TRANSLATION
    assert result.parent_set_id == "set_ko_0001"
    assert result.platform == "xiaohongshu"
    assert result.language == "zh"


def test_every_source_block_gets_a_target_block(copy, ctx):
    """블록이 사라지면 레이아웃에 빈 자리가 남는다."""
    llm = _llm(_localized(copy), _tags())
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)

    source_ids = {b["id"] for s in copy["slides"] for b in s["copy_blocks"]}
    target_ids = {b["id"] for s in result.copy["slides"] for b in s["copy_blocks"]}
    assert target_ids == source_ids


def test_a_dropped_block_fails_loudly(copy, ctx):
    draft = _localized(copy)
    draft.slides[0].blocks.pop()
    llm = _llm(draft, _tags())
    with pytest.raises(LocalizationError, match="빠졌다"):
        Localizer(llm=llm).localize(copy, ctx, **TARGET)


def test_an_invented_block_id_is_rejected(copy, ctx):
    draft = _localized(copy)
    draft.slides[0].blocks.append(LocalizedBlock(id="s01_invented", text="추가"))
    llm = _llm(draft, _tags())
    with pytest.raises(LocalizationError, match="원본에 없는 블록"):
        Localizer(llm=llm).localize(copy, ctx, **TARGET)


def test_layout_template_and_slide_order_are_carried_over(copy, ctx):
    llm = _llm(_localized(copy), _tags())
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)

    assert [s["index"] for s in result.copy["slides"]] == [s["index"] for s in copy["slides"]]
    assert [s["layout_template"] for s in result.copy["slides"]] == [
        s["layout_template"] for s in copy["slides"]
    ]


def test_an_over_limit_headline_is_sent_back_for_shortening(copy, ctx):
    long = {"s01_headline": "专" * 40}
    llm = _llm(_localized(copy, texts=long), _localized(copy), _tags())
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)

    assert result.attempts == 2
    assert "축약" in llm.calls[1].user or "줄여라" in llm.calls[1].user


def test_copy_that_never_fits_fails_instead_of_passing(copy, ctx):
    """절대 규칙 #6 — 재시도가 소진되면 명시적으로 실패한다."""
    long = {"s01_headline": "专" * 40}
    llm = _llm(*[_localized(copy, texts=long) for _ in range(4)], _tags())
    with pytest.raises(LocalizationError, match="축약 후에도"):
        Localizer(llm=llm).localize(copy, ctx, **TARGET)


def test_the_cover_title_limit_is_actually_counted(copy, ctx):
    """샤오홍슈 20자 제한은 프롬프트에 싣는 것만으로 지켜지지 않는다."""
    limit = platform_spec("xiaohongshu").title_max_chars
    over = {"s01_headline": "专" * (limit + 1)}
    llm = _llm(*[_localized(copy, texts=over) for _ in range(4)], _tags())
    with pytest.raises(LocalizationError, match="커버 제목"):
        Localizer(llm=llm).localize(copy, ctx, **TARGET)


def test_the_cover_limit_only_applies_to_the_cover(copy, ctx):
    """20자는 커버 제목의 제약이지 모든 헤드라인의 제약이 아니다."""
    limit = platform_spec("xiaohongshu").title_max_chars
    texts = {"s02_headline": "专" * (limit - 1)}
    llm = _llm(_localized(copy, texts=texts), _tags())
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)
    assert result.copy["slides"][1]["copy_blocks"][1]["text"] == "专" * (limit - 1)


def test_localizing_to_the_same_place_is_refused(copy, dna):
    ctx = AgentContext("a", "instagram", "ko", style_dna=dna)
    with pytest.raises(LocalizationError, match="출발과 도착이 같다"):
        Localizer(llm=_llm()).localize(
            copy, ctx, target_platform="instagram", target_language="ko"
        )


def test_no_style_dna_means_no_localization(copy):
    ctx = AgentContext("a", "instagram", "ko", style_dna=None)
    with pytest.raises(LocalizationError, match="StyleDNA 없이는"):
        Localizer(llm=_llm()).localize(copy, ctx, **TARGET)


def test_the_prompt_forbids_literal_translation(copy, ctx):
    llm = _llm(_localized(copy), _tags())
    Localizer(llm=llm).localize(copy, ctx, **TARGET)
    assert "번역가가 아니다" in llm.calls[0].system
    assert "직역" in llm.calls[0].user


def test_the_prompt_carries_the_measured_limits(copy, ctx):
    capacity = {"headline": RoleCapacity("headline", 3, 2, 888.0)}
    llm = _llm(_localized(copy), _tags())
    Localizer(llm=llm).localize(copy, ctx, capacity=capacity, **TARGET)
    assert "헤드라인 상한: 6자" in llm.calls[0].user


# ── 해시태그 재조사 ─────────────────────────────────────────────────────

def test_hashtags_are_researched_with_search_on(copy, ctx):
    llm = _llm(_localized(copy), _tags())
    Localizer(llm=llm).localize(copy, ctx, **TARGET)
    assert llm.calls[1].search is True


def test_hashtags_are_not_translated_from_the_source(copy, ctx):
    llm = _llm(_localized(copy), _tags())
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)
    assert not set(result.copy["hashtags"]) & set(copy["hashtags"])
    assert all(t["evidence"] for t in result.hashtag_research)


def test_hashtags_without_any_search_evidence_fail(copy, ctx):
    """검색이 아무 페이지도 열지 않았으면 '재조사'가 아니다."""
    llm = _llm(_localized(copy), _tags(), hits=False)
    with pytest.raises(LocalizationError, match="재조사하지 못했다"):
        Localizer(llm=llm).localize(copy, ctx, **TARGET)


def test_hashtags_are_capped_at_the_platform_limit(copy, ctx):
    llm = _llm(_localized(copy), _tags(n=25))
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)
    assert len(result.copy["hashtags"]) == platform_spec("xiaohongshu").hashtag_max


def test_duplicate_tags_are_collapsed(copy, ctx):
    tags = HashtagSet(
        tags=[ResearchedTag(tag="#桌面", kind="broad", evidence="검색 상위") for _ in range(4)]
    )
    llm = _llm(_localized(copy), tags)
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)
    assert result.copy["hashtags"] == ["#桌面"]


# ── 플랫폼 어댑터 ───────────────────────────────────────────────────────

def test_topic_tags_use_the_platform_notation():
    """`#태그` 그대로 넣으면 샤오홍슈에서 话题 태그로 잡히지 않는다."""
    assert adapter_for("xiaohongshu").format_tag("专注力") == "#专注力[话题]#"
    assert adapter_for("instagram").format_tag("#집중력") == "#집중력"


def test_tag_notation_follows_the_spec_not_a_hardcoded_string():
    """절대 규칙 #2 — 표기가 바뀌면 yaml만 고치면 코드는 그대로다."""
    import dataclasses

    adapter = adapter_for("xiaohongshu")
    adapter.spec = dataclasses.replace(adapter.spec, topic_tag_format="[{tag}]")
    assert adapter.format_tag("专注力") == "[专注力]"


def test_a_sparse_cover_is_reported_on_a_high_density_platform(copy, ctx):
    llm = _llm(_localized(copy), _tags())
    result = Localizer(llm=llm).localize(copy, ctx, **TARGET)
    # 데모 커버는 블록 3개라 통과한다. 하나로 줄이면 경고가 붙어야 한다.
    assert not any(w.field == "cover" for w in result.warnings)

    sparse = copy
    sparse["slides"][0]["copy_blocks"] = sparse["slides"][0]["copy_blocks"][:1]
    llm = _llm(_localized(sparse), _tags())
    result = Localizer(llm=llm).localize(sparse, ctx, **TARGET)
    assert any(w.field == "cover" for w in result.warnings)


def test_cover_title_report_reads_the_first_slide(copy):
    report = cover_title_report(copy, "xiaohongshu")
    assert report and "커버 제목" in report[0]


# ── 파이프라인 연결 ─────────────────────────────────────────────────────

def test_run_requires_an_explicit_target(copy, ctx):
    with pytest.raises(LocalizationError, match="대상이 지정되지 않았다"):
        Localizer(llm=_llm()).run({"copy": copy}, ctx)


def test_run_puts_the_variant_in_state(copy, dna):
    ctx = AgentContext(
        "deskreset", "instagram", "ko", style_dna=dna,
        options={"target_platform": "xiaohongshu", "target_language": "zh"},
    )
    llm = _llm(_localized(copy), _tags())
    state = Localizer(llm=llm).run({"copy": copy, "set_id": "set_ko_0001"}, ctx)

    assert state["copy"] is copy                      # 원본을 덮어쓰지 않는다
    assert state["localized"]["parent_set_id"] == "set_ko_0001"
    assert state["localized"]["variant_type"] == "translation"
