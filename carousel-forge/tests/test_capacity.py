"""텍스트 수용량 실측 — 언어를 바꿀 때 글자수 상한을 어림하지 않기 위한 측정.

브라우저를 띄운다. `-m "not browser"`로 건너뛸 수 있다.
"""

from __future__ import annotations

import pytest

from core.agents.localizer import retarget_dna
from core.config import platform_spec
from core.render.capacity import SAMPLES, CapacityError, measure_capacity
from core.render.model import Theme
from tests.fixtures.demo_set import demo_style_dna

pytestmark = pytest.mark.browser


def _theme(dna, platform):
    spec = platform_spec(platform)
    return Theme.from_dna(dna, spec, spec.canvas), spec


@pytest.fixture(scope="module")
def korean(tmp_path_factory):
    theme, spec = _theme(demo_style_dna(), "instagram")
    return measure_capacity(
        theme, spec.canvas, sample=SAMPLES["ko"], work_dir=tmp_path_factory.mktemp("cap_ko")
    )


@pytest.fixture(scope="module")
def chinese(tmp_path_factory):
    dna, _ = retarget_dna(
        demo_style_dna(), target_language="zh", target_platform="xiaohongshu"
    )
    theme, spec = _theme(dna, "xiaohongshu")
    return measure_capacity(
        theme, spec.canvas, sample=SAMPLES["zh"], work_dir=tmp_path_factory.mktemp("cap_zh")
    )


def test_capacity_is_measured_for_every_requested_role(korean):
    assert set(korean) == {"headline", "body", "eyebrow"}
    for cap in korean.values():
        assert cap.chars_per_line > 0
        assert cap.chars == cap.chars_per_line * cap.max_lines


def test_a_smaller_font_fits_more_characters(korean):
    """본문이 헤드라인보다 한 줄에 더 들어가지 않으면 잰 게 아니라 지어낸 값이다."""
    assert korean["body"].chars_per_line > korean["headline"].chars_per_line


def test_the_measured_line_width_matches_the_safe_area(korean):
    spec = platform_spec("instagram")
    theme, _ = _theme(demo_style_dna(), "instagram")
    expected = spec.canvas.width - 2 * theme.safe_margin_px
    assert abs(korean["headline"].line_width_px - expected) < 1.0


def test_chinese_fits_fewer_characters_per_line_than_korean(korean, tmp_path):
    """한자는 한글보다 넓다.

    "중국어는 15~30% 짧다"는 문장만 보고 상한을 올리면 실제로는 넘친다. 같은 폭에
    들어가는 글자 수가 더 적기 때문이다. 캔버스와 여백까지 바꾸면 무엇 때문에 줄었는지
    알 수 없으므로, 여기서는 **같은 인스타그램 캔버스**에 폰트만 바꿔 놓고 잰다.
    """
    dna, _ = retarget_dna(
        demo_style_dna(), target_language="zh", target_platform="instagram"
    )
    theme, spec = _theme(dna, "instagram")
    chinese = measure_capacity(
        theme, spec.canvas, sample=SAMPLES["zh"], work_dir=tmp_path
    )
    assert chinese["headline"].chars_per_line < korean["headline"].chars_per_line
    assert chinese["body"].chars_per_line < korean["body"].chars_per_line


def test_the_target_canvas_changes_the_capacity(korean, chinese):
    """4:5 → 3:4는 여백 규격도 함께 바뀐다. 원본 수치를 그대로 쓰면 안 되는 이유다."""
    assert chinese["headline"].line_width_px != korean["headline"].line_width_px


def test_an_empty_sample_is_refused(tmp_path):
    theme, spec = _theme(demo_style_dna(), "instagram")
    with pytest.raises(CapacityError, match="표본"):
        measure_capacity(theme, spec.canvas, sample="", work_dir=tmp_path)
