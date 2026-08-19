"""M4 — 배경 지시·오토핏·품질 게이트·폐기 재생성 루프.

루프는 스텁으로 검증한다. 브라우저와 모델을 붙이면 느리고 비결정적이 되는데,
정작 확인해야 할 것(몇 번 되감는가, 무엇을 되감는가, 언제 실패하는가)은
전부 결정론적이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agents.art_director import (
    LOW_DETAIL_ZONE,
    ArtDirectionError,
    ArtDirector,
    SlideVisual,
    VisualPlan,
    build_prompt,
)
from core.agents.base import AgentContext
from core.agents.layout_compositor import (
    FIT_STEPS,
    SCRIM_STEPS,
    LayoutCompositor,
    NeedsNewBackground,
    NeedsShorterCopy,
)
from core.agents.quality_gate import (
    Judgement,
    QualityGate,
    QualityGateError,
    QualityReport,
    verdict_for,
)
from core.config import platform_spec
from core.pipeline import ProductionFailed, SetProducer
from core.providers.image import ImageRequest, ProceduralProvider, TextInPromptError
from core.providers.image.base import find_text_requests
from core.render.geometry import Overflow
from core.render.html_renderer import SlideMeasurement
from core.render.model import Theme

FIXTURES = Path(__file__).parent / "fixtures"
DNA = json.loads((FIXTURES / "style_dna_demo.json").read_text(encoding="utf-8"))


@pytest.fixture
def ctx():
    return AgentContext(account_id="a", platform="instagram", language="ko", style_dna=DNA)


@pytest.fixture
def theme():
    spec = platform_spec("instagram")
    return Theme.from_dna(DNA, spec, spec.canvas)


# ── A7 ArtDirector ──────────────────────────────────────────────────────

def _plan():
    return VisualPlan(
        lighting="soft window light, 50mm",
        palette_words="deep charcoal and warm cream",
        slides=[],
    )


def _visual(**kw):
    base = dict(index=1, scene="a quiet desk at dusk", subject="a closed notebook", detail="dust in the air")
    return SlideVisual(**{**base, **kw})


def test_prompt_follows_the_six_block_order(theme):
    prompt = build_prompt(_visual(), _plan(), theme, DNA, canvas_ratio="4:5")
    body = prompt.prompt
    assert body.index("a quiet desk") < body.index("a closed notebook")
    assert body.index("a closed notebook") < body.index("dust in the air")
    assert body.index("dust in the air") < body.index("soft window light")
    assert body.index("soft window light") < body.index("colour palette")


def test_low_detail_zone_comes_from_the_text_zone(theme):
    """텍스트가 얹힐 자리는 비워 두라고 프롬프트에 명시한다."""
    assert theme.text_zone == "bottom"
    prompt = build_prompt(_visual(), _plan(), theme, DNA, canvas_ratio="4:5")
    assert LOW_DETAIL_ZONE["bottom"] in prompt.prompt


def test_negatives_always_include_the_ai_tells(theme):
    prompt = build_prompt(_visual(), _plan(), theme, DNA, canvas_ratio="4:5")
    for must in ("text", "letters", "watermark", "logo", "plastic smooth skin", "oversaturated"):
        assert must in prompt.negative


def test_a_prompt_asking_for_text_is_rejected(theme):
    with pytest.raises(TextInPromptError):
        build_prompt(
            _visual(scene="a wall with the words FOCUS painted on it"),
            _plan(), theme, DNA, canvas_ratio="4:5",
        )


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("글자·숫자·로고가 들어간 표지판은 프레임에서 배제", False),
        ("사물·아이콘·글자 없음", False),
        ("no text, no logos in frame", False),
        ("a poster with the words hello", True),
        ("배경에 텍스트를 넣어라", True),
    ],
)
def test_the_text_guard_understands_negation(text, flagged):
    """잘 쓴 프롬프트일수록 '글자 없음'이라고 적는다. 그걸 요구로 읽으면 안 된다."""
    assert bool(find_text_requests(text)) is flagged


def test_briefs_only_planning_needs_a_brief(ctx):
    outline = {"slides": [{"index": 1, "role": "hook", "visual_brief": "", "single_message": "x"}]}
    with pytest.raises(ArtDirectionError, match="visual_brief가 없다"):
        ArtDirector().plan_from_briefs(outline, ctx)


def test_briefs_only_planning_shares_one_lighting(ctx):
    """세트 전체가 같은 조명이어야 한 계정의 캐러셀로 읽힌다."""
    outline = {
        "slides": [
            {"index": i, "role": "point", "visual_brief": f"a quiet room number {i}",
             "single_message": "x"}
            for i in range(1, 4)
        ]
    }
    prompts = ArtDirector().plan_from_briefs(outline, ctx)
    lightings = {p.blocks["lighting"] for p in prompts}
    styles = {p.blocks["style"] for p in prompts}
    assert len(lightings) == 1 and len(styles) == 1


# ── A8 LayoutCompositor ─────────────────────────────────────────────────

class StubRenderer:
    """정해진 측정값을 돌려주는 렌더러. 조정이 몇 번 도는지 세기 위한 것."""

    def __init__(self, overflow_until: int = 0, contrast_fail_until: int = 0):
        self.overflow_until = overflow_until
        self.contrast_fail_until = contrast_fail_until
        self.calls = 0
        self.seen_fit_scales: list[float] = []

    def render_set(self, render_set, **kwargs):
        self.calls += 1
        self.seen_fit_scales.append(render_set.slides[0].fit_scale)
        return [
            SlideMeasurement(
                index=slide.index,
                role=slide.role,
                layout_template=slide.template(),
                canvas={"width": 1080, "height": 1350},
                safe_area={"x": 92, "y": 92, "width": 896, "height": 1166},
                background=None,
                blocks=[],
                background_png_path=Path("stub.png"),
                source=slide,
            )
            for slide in render_set.slides
        ]


def _stub_set():
    from core.render.model import RenderBlock, RenderSet, RenderSlide

    spec = platform_spec("instagram")
    return RenderSet(
        set_id="s", account="a", platform="instagram", language="ko",
        theme=Theme.from_dna(DNA, spec, spec.canvas),
        slides=[
            RenderSlide(index=1, role="hook",
                        blocks=[RenderBlock(id="s01_headline", role="headline", text="제목")])
        ],
    )


def test_autofit_shrinks_font_before_tracking(monkeypatch, tmp_path):
    """크기를 먼저 줄이고 자간은 나중이다 — 자간부터 줄이면 글자가 붙어 읽기 어렵다."""
    calls = {"n": 0}

    def fake_overflows(measurement):
        calls["n"] += 1
        return [Overflow(1, "s01_headline", "right", 4.0)] if calls["n"] <= 1 else []

    monkeypatch.setattr("core.agents.layout_compositor.find_overflows", fake_overflows)
    monkeypatch.setattr("core.agents.layout_compositor.failing_contrast", lambda m: [])

    renderer = StubRenderer()
    result = LayoutCompositor(renderer=renderer).compose(
        _stub_set(), work_dir=tmp_path, png_dir=tmp_path
    )
    assert result.passes == 2
    assert result.adjustments[0].fit_scale == FIT_STEPS[0][0]
    assert result.adjustments[0].tracking_scale == FIT_STEPS[0][1] == 1.00


def test_exhausted_autofit_asks_for_shorter_copy(monkeypatch, tmp_path):
    """조정으로 안 되면 여기서 카피를 자르지 않는다 — A5에 반송한다."""
    monkeypatch.setattr(
        "core.agents.layout_compositor.find_overflows",
        lambda m: [Overflow(1, "s01_headline", "right", 9.0)],
    )
    monkeypatch.setattr("core.agents.layout_compositor.failing_contrast", lambda m: [])

    with pytest.raises(NeedsShorterCopy) as exc:
        LayoutCompositor(renderer=StubRenderer()).compose(
            _stub_set(), work_dir=tmp_path, png_dir=tmp_path
        )
    assert "카피를 줄여야 한다" in str(exc.value)


def test_contrast_escalates_the_scrim_then_asks_for_a_new_background(monkeypatch, tmp_path):
    from core.render.geometry import ContrastFinding

    monkeypatch.setattr("core.agents.layout_compositor.find_overflows", lambda m: [])
    monkeypatch.setattr(
        "core.agents.layout_compositor.failing_contrast",
        lambda m: [ContrastFinding(1, "s01_headline", 2.1, 4.5, "#ffffff", "#eeeeee")],
    )
    with pytest.raises(NeedsNewBackground) as exc:
        LayoutCompositor(renderer=StubRenderer()).compose(
            _stub_set(), work_dir=tmp_path, png_dir=tmp_path
        )
    assert "배경이 너무 밝거나" in str(exc.value)


def test_scrim_steps_only_increase():
    assert list(SCRIM_STEPS) == sorted(SCRIM_STEPS)
    assert [f for f, _ in FIT_STEPS] == sorted((f for f, _ in FIT_STEPS), reverse=True)


# ── A9 QualityGate ──────────────────────────────────────────────────────

def test_a_single_blocking_failure_fails_the_set():
    report = QualityReport(judgements=[
        Judgement("text_overflow", True, "blocking", "괜찮다", 1),
        Judgement("contrast_below_wcag", False, "blocking", "대비 2.1:1로 기준 미달이다", 2),
    ])
    assert not report.passed
    assert report.failing_slides() == {2}
    assert report.rules_failed() == ["contrast_below_wcag"]


def test_warnings_do_not_block():
    report = QualityReport(judgements=[
        Judgement("hook_strength_low", False, "warning", "훅이 약하다는 판단이다", 1),
    ])
    assert report.passed
    assert len(report.warnings) == 1
    assert str(verdict_for(report)) == "warn"


def test_a_thin_discard_reason_is_rejected():
    """'품질 낮음' 같은 사유로는 무엇을 고쳐야 할지 알 수 없다."""
    gate = QualityGate(use_vision=False)
    report = QualityReport(judgements=[Judgement("text_overflow", False, "blocking", "나쁨", 1)])
    with pytest.raises(QualityGateError, match="사유가 너무 짧다"):
        gate._assert_reasons(report)


def test_missing_background_capture_is_reported_not_assumed():
    """대비를 못 쟀으면 잰 척하지 않는다."""
    gate = QualityGate(use_vision=False)
    measurement = SlideMeasurement(
        index=1, role="hook", layout_template="hook",
        canvas={"width": 1080, "height": 1350},
        safe_area={"x": 92, "y": 92, "width": 896, "height": 1166},
        background=None, blocks=[], background_png_path=None,
    )
    judgements = gate._geometric([measurement], {"text_overflow", "contrast_below_wcag"})
    contrast = next(j for j in judgements if j.rule_id == "contrast_below_wcag")
    assert not contrast.passed
    assert "측정하지 못했다" in contrast.reason


# ── 생산 루프 ───────────────────────────────────────────────────────────

class StubCompositor:
    def __init__(self, renderer):
        self.renderer = renderer

    def compose(self, render_set, **kwargs):
        from core.agents.layout_compositor import CompositionResult, SlideAdjustment

        return CompositionResult(
            measurements=self.renderer.render_set(render_set),
            adjustments=[SlideAdjustment(slide_index=s.index) for s in render_set.slides],
        )


class FailingGate(QualityGate):
    def __init__(self, targets, **kwargs):
        super().__init__(use_vision=False, **kwargs)
        self.targets = targets
        self.rounds = 0

    def judge(self, *, measurements, **kwargs):
        self.rounds += 1
        return QualityReport(judgements=[
            Judgement(
                "ai_text_artifact", m.index not in self.targets, "blocking",
                "주입된 실패 — 되감기와 예산 소진을 검증하기 위한 판정이다.", m.index,
            )
            for m in measurements
        ])


def _copy(count: int = 3):
    return {
        "slides": [
            {
                "index": i, "role": "point", "layout_template": "point",
                "copy_blocks": [
                    {"id": f"s{i:02d}_headline", "role": "headline", "text": "제목", "max_chars": 24}
                ],
            }
            for i in range(1, count + 1)
        ]
    }


def _outline(count: int = 3):
    return {
        "slides": [
            {"index": i, "role": "point", "single_message": "메시지",
             "visual_brief": "a quiet room, no signage"}
            for i in range(1, count + 1)
        ]
    }


def _producer(ctx, tmp_path, gate):
    return SetProducer(
        ctx,
        ProceduralProvider(out_dir=tmp_path / "gen"),
        compositor=StubCompositor(StubRenderer()),
        quality_gate=gate,
        set_id="t",
        use_briefs_only=True,
    )


def test_a_passing_set_needs_one_attempt(ctx, tmp_path):
    gate = FailingGate(targets=set())
    result = _producer(ctx, tmp_path, gate).produce(
        _outline(), _copy(),
        work_dir=tmp_path / "w", png_dir=tmp_path / "p", background_dir=tmp_path / "bg",
    )
    assert len(result.attempts) == 1
    assert result.quality.passed
    assert result.discarded == []


def test_only_the_failing_slide_is_regenerated(ctx, tmp_path):
    """멀쩡한 슬라이드를 다시 만들지 않는다 — 비용도 일관성도 손해다."""
    seen: list[int] = []

    class RecordingProvider(ProceduralProvider):
        def generate(self, request: ImageRequest):
            seen.append(request.seed)
            return super().generate(request)

    provider = RecordingProvider(out_dir=tmp_path / "gen")
    producer = SetProducer(
        ctx, provider,
        compositor=StubCompositor(StubRenderer()),
        quality_gate=FailingGate(targets={2}),
        set_id="t", use_briefs_only=True,
    )
    with pytest.raises(ProductionFailed) as exc:
        producer.produce(
            _outline(), _copy(),
            work_dir=tmp_path / "w", png_dir=tmp_path / "p", background_dir=tmp_path / "bg",
        )

    # 첫 시도에 3장, 이후 재시도마다 1장씩만 만들어야 한다.
    attempts = len(exc.value.log)
    assert len(seen) == 3 + (attempts - 1), f"생성 횟수가 맞지 않는다: {len(seen)}장, 시도 {attempts}회"
    assert all(entry["slides"] == [2] for entry in exc.value.log)


def test_retry_exhaustion_fails_loudly_with_a_log(ctx, tmp_path):
    gate = FailingGate(targets={1})
    with pytest.raises(ProductionFailed) as exc:
        _producer(ctx, tmp_path, gate).produce(
            _outline(), _copy(),
            work_dir=tmp_path / "w", png_dir=tmp_path / "p", background_dir=tmp_path / "bg",
        )
    assert "재시도가 소진됐다" in str(exc.value)
    # 시도가 기록으로 남는다 — 무엇을 몇 번 되감았는지 추적할 수 있어야 한다
    assert len(exc.value.log) >= 2
    assert all(entry["slides"] == [1] for entry in exc.value.log)


def test_regeneration_uses_a_new_seed_each_attempt(ctx, tmp_path):
    """같은 seed로 다시 만들면 같은 그림이 나온다 — 재생성이 재생성이 아니게 된다."""
    seen: list[int] = []

    class RecordingProvider(ProceduralProvider):
        def generate(self, request: ImageRequest):
            seen.append(request.seed)
            return super().generate(request)

    producer = SetProducer(
        ctx,
        RecordingProvider(out_dir=tmp_path / "gen"),
        compositor=StubCompositor(StubRenderer()),
        quality_gate=FailingGate(targets={1}),
        set_id="t",
        use_briefs_only=True,
    )
    with pytest.raises(ProductionFailed):
        producer.produce(
            _outline(1), _copy(1),
            work_dir=tmp_path / "w", png_dir=tmp_path / "p", background_dir=tmp_path / "bg",
        )
    assert len(seen) == len(set(seen)), f"seed가 반복됐다: {seen}"
