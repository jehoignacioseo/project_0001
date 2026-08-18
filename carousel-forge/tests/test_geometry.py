"""대비비 계산 — A9의 contrast_below_wcag 판정이 여기에 기댄다."""

from __future__ import annotations

import pytest

from core.render.geometry import blend, contrast_ratio


def test_black_on_white_is_maximum_contrast():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)


def test_same_color_has_no_contrast():
    assert contrast_ratio("#7f7f7f", "#7f7f7f") == pytest.approx(1.0)


def test_demo_palette_passes_wcag_aa():
    # 크림색 텍스트 / 거의 검은 배경 — 데모 StyleDNA의 조합
    assert contrast_ratio("#f4f1ec", "#111111") > 4.5


def test_scrim_blend_moves_toward_the_overlay_color():
    assert blend("#000000", "#ffffff", 0.5) == "#808080"
    assert blend("#000000", "#ffffff", 0.0) == "#ffffff"
    assert blend("#000000", "#ffffff", 1.0) == "#000000"


def test_rgb_strings_from_the_browser_are_accepted():
    assert contrast_ratio("rgb(0, 0, 0)", "rgb(255, 255, 255)") == pytest.approx(21.0, abs=0.01)
