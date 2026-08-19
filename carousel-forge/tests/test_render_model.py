"""렌더 입력 계약 — 크기는 비율에서, 위반은 예외로."""

from __future__ import annotations

import pytest

from core.config import platform_spec
from core.render.model import RenderBlock, RenderModelError, RenderSet, RenderSlide, Theme
from tests.fixtures.demo_set import demo_render_set, demo_style_dna


def test_type_size_comes_from_ratio_not_pixels():
    """size_ratio는 캔버스 짧은 변 대비 비율이다. 캔버스가 바뀌면 크기도 따라간다."""
    dna = demo_style_dna()
    ig = platform_spec("instagram")
    xhs = platform_spec("xiaohongshu")

    ig_theme = Theme.from_dna(dna, ig, ig.canvas)
    xhs_theme = Theme.from_dna(dna, xhs, xhs.canvas)

    ratio = dna["visual"]["typography"]["headline"]["size_ratio"]
    assert ig_theme.headline.size_px == pytest.approx(ratio * ig.canvas.short_side)
    # 두 플랫폼 모두 짧은 변이 1080이므로 크기는 같게 유지된다 — 이게 비율로 저장하는 이유다.
    assert xhs_theme.headline.size_px == ig_theme.headline.size_px


def test_safe_margin_never_goes_below_platform_minimum():
    dna = demo_style_dna()
    dna["visual"]["layout"]["safe_margin_ratio"] = 0.01   # 플랫폼 최소보다 작게
    spec = platform_spec("instagram")
    theme = Theme.from_dna(dna, spec, spec.canvas)
    assert theme.safe_margin_px == spec.safe_margin_px


def test_char_limit_violation_is_rejected_before_rendering():
    render_set = demo_render_set()
    render_set.slides[0].blocks[1].max_chars = 5
    with pytest.raises(RenderModelError, match="상한 5자를 넘는다"):
        render_set.validate()


def test_slide_count_beyond_platform_limit_is_rejected():
    render_set = demo_render_set()
    spec = platform_spec("instagram")
    extra = [
        RenderSlide(index=i, role="point", blocks=[RenderBlock(id=f"s{i:02d}_body", role="body", text="x")])
        for i in range(10, 10 + spec.max_slides)
    ]
    render_set.slides = render_set.slides + extra
    with pytest.raises(RenderModelError, match="슬라이드 허용 범위"):
        render_set.validate()


def test_emphasis_span_out_of_range_is_rejected():
    with pytest.raises(RenderModelError, match="강조 구간"):
        RenderBlock(id="s01_headline", role="headline", text="짧다", emphasis_spans=[(0, 99)])


def test_segments_split_around_emphasis():
    block = RenderBlock(id="s01_headline", role="headline", text="집중이 끊긴다", emphasis_spans=[(0, 3)])
    assert block.segments() == [("집중이", True), (" 끊긴다", False)]


def test_font_family_is_validated_before_reaching_the_stylesheet():
    render_set = demo_render_set()
    style = render_set.theme.headline
    assert "Pretendard" in style.css_font_family
    with pytest.raises(RenderModelError, match="쓸 수 없는 문자"):
        type(style)(
            family='X"; } body { display:none } #a {',
            fallback=(), weight=400, size_px=10, letter_spacing_em=0, line_height=1,
        ).css_font_family


def test_roles_map_to_the_three_m1_templates():
    render_set = demo_render_set()
    templates = {slide.template() for slide in render_set.slides}
    assert templates <= {"hook", "point", "cta"}
    assert render_set.slides[0].template() == "hook"
    assert render_set.slides[-1].template() == "cta"


def test_unknown_role_is_not_silently_defaulted():
    slide = RenderSlide(index=1, role="mystery", blocks=[])
    with pytest.raises(RenderModelError, match="템플릿이 매핑되지 않은 role"):
        slide.template()


def test_fonts_required_lists_embeddable_files():
    fonts = demo_render_set().fonts_required()
    assert {f["style"] for f in fonts} == {"Regular", "Bold", "ExtraBold"}
    assert all(f["file"].endswith(".woff2") for f in fonts)


def test_every_registered_font_file_exists_with_its_license():
    """폰트를 등록해 놓고 파일이 없으면 렌더가 폴백으로 조용히 떨어진다.

    라이선스도 함께 본다 — OFL은 폰트를 재배포할 때 사본 동봉을 요구하고,
    내보내기 폴더가 곧 재배포다 (절대 규칙 #10).
    """
    from core.config import FONTS_DIR
    from core.render.model import FONT_FILES, FONT_LICENSES

    for (family, _style), filename in FONT_FILES.items():
        assert (FONTS_DIR / filename).exists(), f"{filename}이 없다"
        assert family in FONT_LICENSES, f"{family}의 라이선스 파일이 등록되지 않았다"
        assert (FONTS_DIR / FONT_LICENSES[family]).exists()


def test_the_chinese_font_is_registered_for_every_weight_korean_has():
    """언어를 바꿨을 때 굵기가 하나라도 비면 그 역할만 폴백으로 떨어진다."""
    from core.render.model import FONT_FILES

    korean = {s for (f, s) in FONT_FILES if f == "Pretendard"}
    chinese = {s for (f, s) in FONT_FILES if f == "Noto Sans SC"}
    assert korean <= chinese
