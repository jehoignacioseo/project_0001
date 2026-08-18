"""섹션 6.2 SVG 내보내기 규칙. 텍스트가 편집 불가능해지면 이 프로그램은 실패한 것이다."""

from __future__ import annotations

import pytest

from core.render.svg_exporter import SvgExportError, assert_svg_rules, css_color_to_hex

MINIMAL = '<svg><text id="s01_headline"><tspan x="0" y="10">안녕</tspan></text></svg>'


def test_minimal_svg_passes():
    assert_svg_rules(MINIMAL)


def test_outlined_text_is_rejected():
    with pytest.raises(SvgExportError, match="<path"):
        assert_svg_rules('<svg><path d="M0 0"/><text><tspan>x</tspan></text></svg>')


def test_filters_and_masks_are_rejected():
    for bad in ("<filter", "<mask", "<clipPath"):
        with pytest.raises(SvgExportError):
            assert_svg_rules(f'<svg>{bad} id="a"/><text><tspan>x</tspan></text></svg>')


def test_svg_without_text_is_rejected():
    with pytest.raises(SvgExportError, match="<text> 요소가 하나도 없다"):
        assert_svg_rules('<svg><rect x="0"/></svg>')


def test_css_classes_are_rejected():
    with pytest.raises(SvgExportError, match="CSS 클래스"):
        assert_svg_rules('<svg><text class="headline"><tspan>x</tspan></text></svg>')


@pytest.mark.parametrize(
    ("value", "expected"),
    [("rgb(17, 17, 17)", "#111111"), ("#ABCDEF", "#abcdef"), ("#abc", "#aabbcc"),
     ("rgba(244, 241, 236, 1)", "#f4f1ec")],
)
def test_color_normalisation(value, expected):
    assert css_color_to_hex(value) == expected


def test_unparseable_color_raises():
    with pytest.raises(SvgExportError):
        css_color_to_hex("papayawhip")
