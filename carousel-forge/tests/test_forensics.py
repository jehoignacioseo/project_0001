"""A1의 측정 층 — 색·기하·통계는 모델 없이 잰다.

여기가 틀리면 스타일 추출 전체가 틀린다. 순수 함수라 전부 결정론적으로 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agents.forensics import analyse_captions, analyse_text_zones, compare_dna, delta_e_2000
from core.agents.forensics.captions import _is_hapsyo
from core.agents.forensics.palette import extract_palette
from scripts.make_dummy_backgrounds import gradient_background, write_png

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def flat_images(tmp_path_factory):
    """단색에 가까운 이미지 — 팔레트가 정확히 뭐가 나와야 하는지 아는 상태."""
    root = tmp_path_factory.mktemp("flat")
    paths = []
    for i in range(3):
        path = root / f"flat_{i}.png"
        write_png(path, 80, 100, gradient_background(80, 100, "#204080", "#204080", seed=i, grain=0.0))
        paths.append(path)
    return paths


# ── 팔레트 ──────────────────────────────────────────────────────────────

def test_palette_recovers_a_known_flat_colour(flat_images):
    report = extract_palette(flat_images)
    assert delta_e_2000(report.background.hex, "#204080") < 2.0


def test_palette_is_deterministic(flat_images):
    """같은 이미지에서 항상 같은 팔레트가 나와야 스타일이 재현 가능하다."""
    first = extract_palette(flat_images)
    second = extract_palette(flat_images)
    assert [s.hex for s in first.swatches] == [s.hex for s in second.swatches]


def test_palette_separates_background_text_and_accent(tmp_path):
    """어두운 배경 + 밝은 텍스트 + 채도 높은 액센트를 구분한다."""
    rows = gradient_background(120, 120, "#111111", "#111111", seed=1, grain=0.0)
    for y in range(10, 40):          # 밝은 띠 = 텍스트
        for x in range(0, 120):
            rows[y][x * 3 : x * 3 + 3] = bytearray([0xF4, 0xF1, 0xEC])
    for y in range(60, 70):          # 좁은 액센트 띠
        for x in range(0, 120):
            rows[y][x * 3 : x * 3 + 3] = bytearray([0xC8, 0xA1, 0x5A])
    path = tmp_path / "three.png"
    write_png(path, 120, 120, rows)

    report = extract_palette([path])
    assert delta_e_2000(report.background.hex, "#111111") < 4
    assert delta_e_2000(report.text.hex, "#f4f1ec") < 4
    assert delta_e_2000(report.accent.hex, "#c8a15a") < 6


def test_usage_ratio_sums_to_one(flat_images):
    ratio = extract_palette(flat_images).usage_ratio()
    assert abs(sum(ratio.values()) - 1.0) < 0.01


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="이미지가 없다"):
        extract_palette([])


# ── 색차 ────────────────────────────────────────────────────────────────

def test_delta_e_is_zero_for_identical_colours():
    assert delta_e_2000("#c8a15a", "#c8a15a") == pytest.approx(0.0, abs=1e-9)


def test_delta_e_grows_with_perceived_difference():
    near = delta_e_2000("#111111", "#161515")
    far = delta_e_2000("#faf7f2", "#111111")
    assert near < 3 < far


# ── 캡션 통계 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        ("나옵니다", True), ("냅니다", True), ("됩니다", True), ("습니다", True),
        ("확실합니다", True), ("아니다", False), ("한다", False), ("계신가요", False),
    ],
)
def test_hapsyo_detection_handles_composed_hangul(tail, expected):
    """한글 음절은 결합 문자다. "ㅂ니다" 리터럴 비교로는 "나옵니다"가 안 걸린다."""
    assert _is_hapsyo(tail) is expected


def test_formal_endings_are_not_misread_as_casual():
    """-습니다로 끝나는 문장이 반말로 분류되면 카피 말투가 통째로 어긋난다."""
    stats = analyse_captions(["오늘도 확인합니다. 결과가 나옵니다. 비용이 줄어듭니다."])
    assert "반말" not in stats.register
    assert "존댓말" in stats.register


def test_haeyo_register_is_detected():
    stats = analyse_captions(["오늘부터 시작해요. 저장해두세요. 같이 해봐요."])
    assert stats.register == "해요체"


def test_mixed_register_is_reported_as_mixed():
    """표가 갈리면 하나로 단정하지 않는다 — 실제 계정은 섞어 쓴다."""
    stats = analyse_captions(
        ["확인해 보세요. 도움이 됩니다. 시작해요. 좋습니다. 해보세요. 편합니다."]
    )
    assert "혼용" in stats.register


def test_emoji_density_and_palette_are_counted():
    stats = analyse_captions(["오늘은 여기까지예요 ✨", "내일 또 만나요 ✨"])
    assert stats.emoji_density > 0
    assert stats.emoji_palette[0] == "✨"


def test_hashtags_are_stripped_from_the_body_and_counted():
    stats = analyse_captions(["본문입니다.\n#태그하나 #태그둘 #태그셋"])
    assert stats.hashtag_count_avg == 3
    assert stats.hashtag_placement == "end"


def test_repeated_phrases_surface_as_signature_candidates():
    captions = ["오늘 바로 확인해 보세요."] * 4 + ["다른 이야기입니다."]
    assert any("오늘 바로" in p for p in analyse_captions(captions).repeated_phrases)


def test_empty_captions_are_rejected():
    with pytest.raises(ValueError, match="캡션이 없다"):
        analyse_captions([])


# ── 텍스트 영역 기하 ────────────────────────────────────────────────────

def _write_text_like(path: Path, *, bands: list[tuple[int, int, int, int]]) -> None:
    """흰 바탕에 검은 막대를 그려 글줄을 흉내 낸다. (top, bottom, left, right)"""
    rows = gradient_background(200, 200, "#ffffff", "#ffffff", seed=1, grain=0.0)
    for top, bottom, left, right in bands:
        for y in range(top, bottom):
            for x in range(left, right):
                rows[y][x * 3 : x * 3 + 3] = bytearray([0, 0, 0])
    write_png(path, 200, 200, rows)


def test_left_aligned_lines_are_detected(tmp_path):
    path = tmp_path / "left.png"
    _write_text_like(path, bands=[(20, 30, 20, 170), (40, 50, 20, 120), (60, 70, 20, 90)])
    assert analyse_text_zones([path]).alignment == "left"


def test_centre_aligned_lines_are_detected(tmp_path):
    path = tmp_path / "centre.png"
    _write_text_like(path, bands=[(20, 30, 25, 175), (40, 50, 50, 150), (60, 70, 65, 135)])
    assert analyse_text_zones([path]).alignment == "center"


def test_a_short_left_badge_does_not_override_centred_headlines(tmp_path):
    """뱃지 같은 짧은 조각이 긴 줄의 정렬을 뒤집으면 안 된다."""
    path = tmp_path / "badge.png"
    _write_text_like(
        path,
        bands=[(10, 18, 20, 50), (30, 45, 25, 175), (55, 70, 45, 155), (80, 95, 60, 140)],
    )
    assert analyse_text_zones([path]).alignment == "center"


def test_text_zone_follows_where_the_ink_sits(tmp_path):
    top_path, bottom_path = tmp_path / "t.png", tmp_path / "b.png"
    _write_text_like(top_path, bands=[(20, 30, 20, 170), (40, 50, 20, 120)])
    _write_text_like(bottom_path, bands=[(150, 160, 20, 170), (170, 180, 20, 120)])
    assert analyse_text_zones([top_path]).text_zone == "top"
    assert analyse_text_zones([bottom_path]).text_zone == "bottom"


def test_safe_margin_comes_from_the_widest_slide(tmp_path):
    """여백은 가장 넓게 뻗은 장이 드러낸다. 짧은 장의 여백을 쓰면 과대평가된다."""
    wide, narrow = tmp_path / "wide.png", tmp_path / "narrow.png"
    _write_text_like(wide, bands=[(20, 30, 20, 180), (40, 50, 20, 150)])
    _write_text_like(narrow, bands=[(20, 30, 60, 140), (40, 50, 60, 120)])
    report = analyse_text_zones([wide, narrow])
    assert report.safe_margin_ratio == pytest.approx(0.10, abs=0.03)


def test_blank_images_do_not_fabricate_a_zone(tmp_path):
    path = tmp_path / "blank.png"
    write_png(path, 100, 100, gradient_background(100, 100, "#ffffff", "#ffffff", seed=1, grain=0.0))
    report = analyse_text_zones([path])
    assert report.samples == 0      # 못 쟀으면 못 쟀다고 말한다


# ── 왕복 대조 ───────────────────────────────────────────────────────────

def test_identical_dna_compares_as_a_perfect_match():
    dna = json.loads((FIXTURES / "style_dna_benchmark.json").read_text(encoding="utf-8"))
    comparison = compare_dna(dna, dna)
    assert comparison.score == 1.0


def test_comparison_separates_measured_from_interpreted():
    dna = json.loads((FIXTURES / "style_dna_benchmark.json").read_text(encoding="utf-8"))
    comparison = compare_dna(dna, dna)
    assert comparison.measured() and comparison.interpreted()
    assert len(comparison.measured()) + len(comparison.interpreted()) == len(comparison.matches)


def test_palette_drift_is_caught():
    dna = json.loads((FIXTURES / "style_dna_benchmark.json").read_text(encoding="utf-8"))
    drifted = json.loads(json.dumps(dna))
    drifted["visual"]["palette"]["background"] = ["#2a5f1f"]
    failures = [m for m in compare_dna(dna, drifted).matches if not m.ok]
    assert any(m.field == "palette.background" for m in failures)


# ── A1 에이전트 ─────────────────────────────────────────────────────────

def _interpretation(**overrides):
    from core.agents.style_forensics import Interpretation

    base = dict(
        archetype="editorial-minimal", one_line="한 줄", target_reader="독자",
        headline_family_class="sans", headline_weight=700, headline_size_ratio=0.08,
        headline_letter_spacing_em=-0.02, headline_line_height=1.2, headline_case="as-is",
        body_size_ratio=0.035, body_line_height=1.6, accent_size_ratio=0.026,
        mixed_script_rule="Pretendard 우선", text_block_max_lines=4, grid="single",
        decorations=["divider-rule"], photo_ratio=0.6, illustration_ratio=0.2,
        solid_ratio=0.2, treatment=["film-grain"], grain_intensity=0.3,
        subject_rules="인물 드묾", overlay_type="none", overlay_opacity=0.0,
        slide_count_min=6, slide_count_max=9, slide_count_mode=8, hook_type="question",
        narrative_pattern="listicle",
        slide_roles_sequence=["hook", "point", "summary", "cta"], cta_type="save",
        cover_rule="title+sub", headline_char_limit=24, body_char_limit_per_slide=80,
        signature_phrases=[], forbidden_words=["대박"], first_line_rule="질문으로 연다",
        hashtag_broad=3, hashtag_niche=5, hashtag_branded=1, hashtag_community=1,
        notes="메모", low_confidence_fields=[],
    )
    return Interpretation(**{**base, **overrides})


def _feed(tmp_path, count):
    paths = []
    for i in range(count):
        path = tmp_path / f"f{i}.png"
        _write_text_like(path, bands=[(20, 32, 20, 170), (40, 52, 20, 120)])
        paths.append(path)
    return paths


def test_fewer_than_six_samples_caps_confidence_below_the_threshold(tmp_path):
    """스펙의 추출 규칙: 샘플 6장 미만이면 confidence < 0.6이고 경고한다."""
    from core.agents.base import AgentContext
    from core.agents.style_forensics import StyleForensics
    from core.providers.llm import ScriptedLLM

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    result = StyleForensics(llm=ScriptedLLM(responses=[_interpretation()])).extract(
        _feed(tmp_path, 3), captions=["오늘부터 시작해요."], ctx=ctx
    )
    assert result.confidence_score < 0.6
    assert any("최소 6장" in w for w in result.warnings)


def test_missing_captions_lower_confidence_and_warn(tmp_path):
    from core.agents.base import AgentContext
    from core.agents.style_forensics import StyleForensics
    from core.providers.llm import ScriptedLLM

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    without = StyleForensics(llm=ScriptedLLM(responses=[_interpretation()])).extract(
        _feed(tmp_path, 8), captions=[], ctx=ctx
    )
    with_captions = StyleForensics(llm=ScriptedLLM(responses=[_interpretation()])).extract(
        _feed(tmp_path, 8), captions=["오늘부터 시작해요. 저장해두세요."], ctx=ctx
    )
    assert without.confidence_score < with_captions.confidence_score
    assert any("캡션이 주어지지 않아" in w for w in without.warnings)


def test_measured_values_win_over_the_model(tmp_path):
    """모델이 뭐라 답하든 픽셀·기하에서 잰 값이 DNA에 실린다."""
    from core.agents.base import AgentContext
    from core.agents.style_forensics import StyleForensics
    from core.providers.llm import ScriptedLLM

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    result = StyleForensics(llm=ScriptedLLM(responses=[_interpretation()])).extract(
        _feed(tmp_path, 6), captions=["오늘부터 시작해요."], ctx=ctx
    )
    layout = result.dna["visual"]["layout"]
    assert layout["text_zone"] == result.zones.text_zone
    assert layout["alignment"] == result.zones.alignment
    assert result.dna["visual"]["palette"]["background"] == [result.palette.background.hex]
    # 캡션 통계가 있으면 모델의 register 추정이 아니라 센 값이 들어간다
    assert result.dna["copy"]["register"] == result.captions.register


def test_role_sequence_is_repaired_to_start_with_hook_and_end_with_cta(tmp_path):
    from core.agents.base import AgentContext
    from core.agents.style_forensics import StyleForensics
    from core.providers.llm import ScriptedLLM

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    result = StyleForensics(
        llm=ScriptedLLM(responses=[_interpretation(slide_roles_sequence=["point", "cta", "proof"])])
    ).extract(_feed(tmp_path, 6), captions=["오늘부터 시작해요."], ctx=ctx)
    roles = result.dna["structure"]["slide_roles_sequence"]
    assert roles[0] == "hook" and roles[-1] == "cta"


def test_the_interpretation_model_blocks_out_of_range_values():
    """1차 방어선 — 구조화 출력 단계에서 애초에 못 나오게 막는다."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _interpretation(headline_char_limit=0)
    with pytest.raises(ValidationError):
        _interpretation(narrative_pattern="자유롭게 서술한 패턴")


def test_extracted_dna_is_validated_against_the_schema():
    """2차 방어선 — 조립된 DNA가 계약을 어기면 내보내지 않는다."""
    from core.agents.style_forensics import ForensicsError, StyleForensics

    dna = json.loads((FIXTURES / "style_dna_benchmark.json").read_text(encoding="utf-8"))
    dna["visual"]["palette"]["background"] = ["짙은 회색"]     # hex가 아니다
    with pytest.raises(ForensicsError, match="스키마를 어겼다"):
        StyleForensics(llm=None)._validate(dna)


def test_missing_screenshot_files_are_reported(tmp_path):
    from core.agents.base import AgentContext
    from core.agents.style_forensics import ForensicsError, StyleForensics
    from core.providers.llm import ScriptedLLM

    ctx = AgentContext(account_id="a", platform="instagram", language="ko")
    with pytest.raises(ForensicsError, match="찾을 수 없다"):
        StyleForensics(llm=ScriptedLLM(responses=[])).extract(
            [tmp_path / "없음.png"], captions=[], ctx=ctx
        )
