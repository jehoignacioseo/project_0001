"""플랫폼 규격은 코드가 아니라 설정에서 온다 (절대 규칙 #2)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.config import (
    ConfigError,
    platform_keys,
    platform_spec,
    platforms_are_stale,
    platforms_verified_at,
    quality_rules,
)


def test_known_platforms():
    assert set(platform_keys()) == {"instagram", "xiaohongshu"}


def test_instagram_spec_matches_yaml():
    spec = platform_spec("instagram")
    assert (spec.canvas.width, spec.canvas.height) == (1080, 1350)
    assert spec.canvas.short_side == 1080
    assert spec.caption_fold_at == 125
    assert spec.max_slides == 20


def test_xiaohongshu_title_limit_is_the_hard_constraint():
    spec = platform_spec("xiaohongshu")
    assert spec.title_max_chars == 20
    assert (spec.canvas.width, spec.canvas.height) == (1080, 1440)


def test_unknown_platform_raises_rather_than_guessing():
    with pytest.raises(ConfigError, match="알 수 없는 플랫폼"):
        platform_spec("threads")


def test_alt_canvas_lookup():
    spec = platform_spec("instagram")
    assert spec.canvas_for("square").height == 1080
    assert spec.canvas_for() is spec.canvas
    with pytest.raises(ConfigError):
        spec.canvas_for("nope")


def test_staleness_is_reported():
    verified = platforms_verified_at()
    assert verified is not None
    assert not platforms_are_stale(verified + timedelta(days=1))
    assert platforms_are_stale(verified + timedelta(days=400))


def test_quality_rules_have_blocking_and_retry_budget():
    rules = quality_rules()
    ids = {r["id"] for r in rules["blocking"]}
    # 폐기 사유는 파이프라인 되감기 지점과 짝을 이뤄야 한다.
    assert {"text_overflow", "contrast_below_wcag", "factcheck_false"} <= ids
    assert rules["retry"]["on_exhaust"] == "fail_loudly"


def test_verified_at_is_not_in_the_future():
    assert platforms_verified_at() <= date.today()
