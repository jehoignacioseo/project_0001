"""A8 LayoutCompositor — 배경 + 카피를 합쳐 안전영역과 대비를 맞춘다.

렌더 자체는 M1의 `core.render`가 한다. 이 에이전트가 하는 일은 **맞을 때까지
조정하는 것**이다.

  오토핏 (안전영역 침범 시, 이 순서로):
    ① 폰트 크기 -5%  ② 자간 축소  ③ 줄바꿈 재계산(줄어든 크기로 자동)
    ④ 그래도 넘치면 A5에 카피 축약을 요청한다 (여기서 임의로 자르지 않는다)

  대비 (WCAG 미달 시):
    ① 스크림 오버레이를 단계적으로 올린다
    ② 한계까지 올려도 안 되면 배경 재생성을 요청한다 (A7으로 반송)

조정은 StyleDNA를 건드리지 않는다. 스타일은 하드 제약이고(절대 규칙 #8), 여기서
줄이는 것은 **이 슬라이드의 표시 배율**일 뿐이다. 조정 내역은 전부 기록에 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.api.models import PipelineStage
from core.agents.base import Agent, AgentContext
from core.render.geometry import ContrastFinding, Overflow, failing_contrast, find_overflows
from core.render.html_renderer import SlideMeasurement, SlideRenderer
from core.render.model import RenderSet, RenderSlide

#: 오토핏 단계. 스펙의 순서를 그대로 옮긴 것 — 크기를 먼저 줄이고 자간은 나중이다.
#: 자간부터 줄이면 글자가 붙어 읽기 어려워지는데, 크기는 5% 줄여도 티가 덜 난다.
FIT_STEPS: tuple[tuple[float, float], ...] = (
    (0.95, 1.00),
    (0.95, 0.85),
    (0.90, 0.85),
    (0.86, 0.75),
)

#: 대비 확보용 스크림을 올리는 단계.
SCRIM_STEPS: tuple[float, ...] = (0.15, 0.30, 0.45, 0.60)


class CompositionError(RuntimeError):
    """조정으로 해결되지 않는다. 상위(A5/A7)에 반송해야 한다."""


class NeedsShorterCopy(CompositionError):
    """오토핏을 다 써도 카피가 안 들어간다. A5에 축약을 요청해야 한다."""

    def __init__(self, overflows: list[Overflow]) -> None:
        self.overflows = overflows
        detail = "\n".join(f"  - {o}" for o in overflows)
        super().__init__(
            "폰트 축소·자간 축소를 모두 적용해도 카피가 안전영역을 넘는다. "
            f"카피를 줄여야 한다:\n{detail}"
        )


class NeedsNewBackground(CompositionError):
    """스크림을 한계까지 올려도 대비가 안 나온다. A7에 배경 재생성을 요청해야 한다."""

    def __init__(self, findings: list[ContrastFinding]) -> None:
        self.findings = findings
        detail = "\n".join(f"  - {f}" for f in findings)
        super().__init__(
            "스크림을 한계까지 올려도 WCAG 대비에 미달한다. 배경이 너무 밝거나 "
            f"복잡하다 — 재생성이 필요하다:\n{detail}"
        )


@dataclass
class SlideAdjustment:
    slide_index: int
    fit_scale: float = 1.0
    tracking_scale: float = 1.0
    overlay_boost: float = 0.0
    fit_steps_used: int = 0
    scrim_steps_used: int = 0

    def describe(self) -> str:
        bits = []
        if self.fit_scale != 1.0:
            bits.append(f"폰트 {self.fit_scale:.0%}")
        if self.tracking_scale != 1.0:
            bits.append(f"자간 {self.tracking_scale:.0%}")
        if self.overlay_boost:
            bits.append(f"스크림 +{self.overlay_boost:.2f}")
        return f"슬라이드 {self.slide_index}: " + (", ".join(bits) if bits else "조정 없음")


@dataclass
class CompositionResult:
    measurements: list[SlideMeasurement]
    adjustments: list[SlideAdjustment] = field(default_factory=list)
    passes: int = 1

    @property
    def adjusted(self) -> list[SlideAdjustment]:
        return [a for a in self.adjustments if a.fit_steps_used or a.scrim_steps_used]

    def summary(self) -> str:
        lines = [f"합성 {len(self.measurements)}장 · 렌더 {self.passes}회"]
        if self.adjusted:
            lines.append("  조정된 슬라이드:")
            lines += [f"    {a.describe()}" for a in self.adjusted]
        else:
            lines.append("  조정 없이 통과")
        return "\n".join(lines)


class LayoutCompositor(Agent):
    name = "A8 LayoutCompositor"
    stage = PipelineStage.COMPOSE
    milestone = "M4"

    def __init__(self, renderer: SlideRenderer | None = None) -> None:
        self.renderer = renderer or SlideRenderer()

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        raise NotImplementedError(
            "A8은 상태 딕셔너리가 아니라 RenderSet을 받는다. compose()를 직접 호출하라."
        )

    def compose(
        self,
        render_set: RenderSet,
        *,
        work_dir: Path,
        png_dir: Path,
        background_dir: Path | None = None,
        image_format: str = "png",
        quality: int | None = None,
        check_contrast: bool = True,
    ) -> CompositionResult:
        """맞을 때까지 조정하며 렌더한다.

        전체를 다시 렌더하지 않는다. 문제가 있는 슬라이드만 조정해 다시 재는 것이
        렌더 비용 면에서도, 멀쩡한 슬라이드를 건드리지 않는다는 면에서도 맞다.
        """
        adjustments = {s.index: SlideAdjustment(slide_index=s.index) for s in render_set.slides}
        passes = 0

        while True:
            passes += 1
            measurements = self.renderer.render_set(
                render_set,
                work_dir=work_dir,
                png_dir=png_dir,
                background_dir=background_dir,
                image_format=image_format,
                quality=quality,
                capture_background=check_contrast,
            )
            by_index = {m.index: m for m in measurements}
            slides = {s.index: s for s in render_set.slides}

            changed = False
            pending_overflow: list[Overflow] = []
            pending_contrast: list[ContrastFinding] = []

            for index, measurement in by_index.items():
                slide, adjustment = slides[index], adjustments[index]

                overflows = find_overflows(measurement)
                if overflows:
                    if adjustment.fit_steps_used >= len(FIT_STEPS):
                        pending_overflow += overflows
                        continue
                    fit, tracking = FIT_STEPS[adjustment.fit_steps_used]
                    adjustment.fit_steps_used += 1
                    adjustment.fit_scale = fit
                    adjustment.tracking_scale = tracking
                    slide.fit_scale = fit
                    slide.tracking_scale = tracking
                    changed = True
                    continue

                if not check_contrast:
                    continue
                failures = failing_contrast(measurement)
                if not failures:
                    continue
                if adjustment.scrim_steps_used >= len(SCRIM_STEPS):
                    pending_contrast += failures
                    continue
                boost = SCRIM_STEPS[adjustment.scrim_steps_used]
                adjustment.scrim_steps_used += 1
                adjustment.overlay_boost = boost
                slide.overlay_boost = boost
                changed = True

            if pending_overflow:
                raise NeedsShorterCopy(pending_overflow)
            if pending_contrast:
                raise NeedsNewBackground(pending_contrast)
            if not changed:
                return CompositionResult(
                    measurements=measurements,
                    adjustments=list(adjustments.values()),
                    passes=passes,
                )


def apply_adjustments(render_set: RenderSet, adjustments: list[SlideAdjustment]) -> None:
    """조정 결과를 RenderSet에 되돌려 심는다 (재렌더·내보내기에서 그대로 쓰이도록)."""
    by_index = {a.slide_index: a for a in adjustments}
    for slide in render_set.slides:
        adjustment = by_index.get(slide.index)
        if adjustment is None:
            continue
        slide.fit_scale = adjustment.fit_scale
        slide.tracking_scale = adjustment.tracking_scale
        slide.overlay_boost = adjustment.overlay_boost
