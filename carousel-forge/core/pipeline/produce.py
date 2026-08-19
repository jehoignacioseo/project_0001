"""세트 생산 — A7 → A8 → A9와 폐기·재생성 루프.

M4의 완료 기준이 여기 있다: 스타일 + 주제 → 완성 캐러셀 1세트, 그리고 **폐기·
재생성 루프가 실제로 도는 것**.

루프의 규칙은 하나다. QualityGate가 폐기를 판정하면 통과시키지 않는다. 문제가
생긴 슬라이드만 되감아 다시 만들고, `config/quality_rules.yaml`의 재시도 예산이
바닥나면 조용히 넘어가는 대신 **명시적으로 실패한다** (절대 규칙 #6).

폐기된 결과물도 사유와 함께 전부 남는다 (절대 규칙 #9). 폐기본은 지우는 대상이
아니라 품질 패턴 학습 자산이다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel import Session

from apps.api.models import (
    Asset,
    AssetKind,
    GenerationLog,
    GenerationVerdict,
    PipelineStage,
)
from core.agents.art_director import ArtDirector, BackgroundPrompt
from core.agents.base import AgentContext
from core.agents.layout_compositor import (
    CompositionResult,
    LayoutCompositor,
    NeedsNewBackground,
    NeedsShorterCopy,
    apply_adjustments,
)
from core.agents.quality_gate import QualityGate, QualityReport, verdict_for
from core.config import platform_spec
from core.pipeline.retry import RetryBudget, RetryExhausted
from core.pipeline.states import rewind_for
from core.providers.image import ImageProvider, ImageRequest
from core.render.model import RenderBlock, RenderSet, RenderSlide, Theme


class ProductionFailed(RuntimeError):
    """재시도 예산이 바닥났다. 애매한 결과물을 넘기지 않는다."""

    def __init__(self, message: str, *, attempts: int, log: list[dict[str, Any]]) -> None:
        self.attempts = attempts
        self.log = log
        super().__init__(message)


@dataclass
class Attempt:
    number: int
    stage: PipelineStage
    verdict: GenerationVerdict
    reason: str
    slide_indexes: list[int] = field(default_factory=list)
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.number,
            "stage": str(self.stage),
            "verdict": str(self.verdict),
            "reason": self.reason,
            "slides": self.slide_indexes,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ProductionResult:
    render_set: RenderSet
    composition: CompositionResult
    quality: QualityReport
    prompts: list[BackgroundPrompt]
    attempts: list[Attempt] = field(default_factory=list)
    discarded: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"세트 {self.render_set.set_id}: 슬라이드 {len(self.render_set.slides)}장",
            f"  생산 시도 {len(self.attempts)}회 · 폐기 {len(self.discarded)}건",
            self.composition.summary(),
            self.quality.summary(),
        ]
        if self.discarded:
            lines.append("  폐기 내역 (전부 보존된다):")
            for item in self.discarded:
                lines.append(f"    - 슬라이드 {item['slide_index']}: {item['reason'][:100]}")
        return "\n".join(lines)


class SetProducer:
    """배경 생성 → 합성 → 품질 판정을 예산 안에서 반복한다."""

    def __init__(
        self,
        ctx: AgentContext,
        image_provider: ImageProvider,
        *,
        art_director: ArtDirector | None = None,
        compositor: LayoutCompositor | None = None,
        quality_gate: QualityGate | None = None,
        session: Session | None = None,
        set_id: str = "set",
        account: str = "account",
        use_briefs_only: bool = False,
    ) -> None:
        self.ctx = ctx
        self.provider = image_provider
        self.art_director = art_director or ArtDirector()
        self.compositor = compositor or LayoutCompositor()
        self.quality_gate = quality_gate or QualityGate()
        self.session = session
        self.set_id = set_id
        self.account = account
        #: True면 A7이 모델을 부르지 않고 A4의 visual_brief만으로 프롬프트를 짠다.
        self.use_briefs_only = use_briefs_only
        self.budget = RetryBudget.from_config()

    # ── 공개 진입점 ─────────────────────────────────────────────────────
    def produce(
        self,
        outline: dict[str, Any],
        copy: dict[str, Any],
        *,
        work_dir: Path,
        png_dir: Path,
        background_dir: Path,
    ) -> ProductionResult:
        prompts = (
            self.art_director.plan_from_briefs(outline, self.ctx)
            if self.use_briefs_only
            else self.art_director.plan(outline, self.ctx)
        )
        by_index = {p.slide_index: p for p in prompts}

        backgrounds: dict[int, Path] = {}
        attempts: list[Attempt] = []
        discarded: list[dict[str, Any]] = []
        regenerate = [s["index"] for s in copy["slides"]]
        attempt_number = 0

        while True:
            attempt_number += 1
            started = time.monotonic()

            for index in regenerate:
                backgrounds[index] = self._generate_background(
                    by_index[index], background_dir, attempt=attempt_number
                )

            render_set = self._build_render_set(copy, backgrounds, background_dir)

            try:
                composition = self.compositor.compose(
                    render_set,
                    work_dir=work_dir,
                    png_dir=png_dir,
                    background_dir=background_dir,
                    image_format=platform_spec(self.ctx.platform).export_format[0],
                    quality=platform_spec(self.ctx.platform).quality,
                )
            except NeedsShorterCopy as exc:
                # 되감기 지점은 states.REWIND_TARGET이 정한다 — 임의로 고르지 않는다.
                self._record(
                    attempts, attempt_number, rewind_for("text_overflow"),
                    GenerationVerdict.DISCARD, str(exc),
                    [o.slide_index for o in exc.overflows], started,
                )
                raise ProductionFailed(
                    f"카피가 안전영역에 들어가지 않는다. A5로 반송해야 한다:\n{exc}",
                    attempts=attempt_number,
                    log=[a.as_dict() for a in attempts],
                ) from exc
            except NeedsNewBackground as exc:
                failing = sorted({f.slide_index for f in exc.findings})
                reason = str(exc)
                self._record(
                    attempts, attempt_number, rewind_for("contrast_below_wcag"),
                    GenerationVerdict.DISCARD, reason, failing, started,
                )
                regenerate = self._consume_budget(failing, reason, attempts, attempt_number)
                discarded += self._discard_backgrounds(backgrounds, failing, reason)
                continue

            apply_adjustments(render_set, composition.adjustments)
            quality = self.quality_gate.judge(
                measurements=composition.measurements,
                ctx=self.ctx,
                rendered_dna=self.ctx.style_dna,
                backgrounds=backgrounds,
            )
            verdict = verdict_for(quality)
            reason = quality.summary()
            failing = sorted(quality.failing_slides())
            self._record(
                attempts, attempt_number, PipelineStage.QUALITY_GATE, verdict, reason,
                failing, started,
            )

            if quality.passed:
                return ProductionResult(
                    render_set=render_set,
                    composition=composition,
                    quality=quality,
                    prompts=prompts,
                    attempts=attempts,
                    discarded=discarded,
                )

            if not failing:
                # 슬라이드를 특정하지 못하는 실패는 되감을 곳이 없다.
                raise ProductionFailed(
                    "품질 게이트가 세트 전체를 폐기했는데 문제 슬라이드를 특정하지 "
                    f"못했다. 사람이 봐야 한다:\n{reason}",
                    attempts=attempt_number,
                    log=[a.as_dict() for a in attempts],
                )

            regenerate = self._consume_budget(failing, reason, attempts, attempt_number)
            discarded += self._discard_backgrounds(backgrounds, failing, reason)

    # ── 내부 ────────────────────────────────────────────────────────────
    def _consume_budget(
        self,
        failing: list[int],
        reason: str,
        attempts: list[Attempt],
        attempt_number: int,
    ) -> list[int]:
        try:
            for index in failing:
                self.budget.consume(index, reason)
        except RetryExhausted as exc:
            raise ProductionFailed(
                f"{exc}\n\n재시도가 소진됐다. 조용히 통과시키지 않는다 "
                f"(on_exhaust: fail_loudly). 마지막 판정:\n{reason}",
                attempts=attempt_number,
                log=[a.as_dict() for a in attempts],
            ) from exc
        return failing

    def _generate_background(
        self, prompt: BackgroundPrompt, background_dir: Path, *, attempt: int
    ) -> Path:
        spec = platform_spec(self.ctx.platform)
        # 재생성마다 seed를 바꾼다. 같은 seed로 다시 만들면 같은 결과가 나와서
        # 재생성이 재생성이 아니게 된다.
        seed = abs(hash((prompt.prompt, attempt))) % 2**31
        result = self.provider.generate(
            ImageRequest(
                prompt=prompt.prompt,
                width=spec.canvas.width,
                height=spec.canvas.height,
                negative=prompt.negative,
                seed=seed,
            )
        )
        source = Path(result.path)
        target = background_dir / f"bg_{prompt.slide_index:02d}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            target.write_bytes(source.read_bytes())

        self._persist_asset(
            kind=AssetKind.BACKGROUND,
            path=str(target),
            width=result.width,
            height=result.height,
            provider=result.provider,
            prompt=prompt.prompt,
            seed=seed,
        )
        return target

    def _build_render_set(
        self, copy: dict[str, Any], backgrounds: dict[int, Path], background_dir: Path
    ) -> RenderSet:
        dna = self.ctx.style_dna
        spec = platform_spec(self.ctx.platform)
        theme = Theme.from_dna(dna, spec, spec.canvas)

        slides = []
        for slide in copy["slides"]:
            index = slide["index"]
            background = backgrounds.get(index)
            slides.append(
                RenderSlide(
                    index=index,
                    role=slide["role"],
                    layout_template=slide["layout_template"],
                    background=background.name if background else None,
                    background_fill=None if background else theme.palette_background,
                    blocks=[
                        RenderBlock(
                            id=b["id"],
                            role=b["role"],
                            text=b["text"],
                            max_chars=b.get("max_chars"),
                            emphasis_spans=[tuple(s) for s in b.get("emphasis_spans", [])],
                        )
                        for b in slide["copy_blocks"]
                    ],
                )
            )
        return RenderSet(
            set_id=self.set_id,
            account=self.account,
            platform=self.ctx.platform,
            language=self.ctx.language,
            theme=theme,
            slides=slides,
        )

    def _discard_backgrounds(
        self, backgrounds: dict[int, Path], failing: list[int], reason: str
    ) -> list[dict[str, Any]]:
        """폐기 기록. 파일도 레코드도 지우지 않는다 (절대 규칙 #9)."""
        out = []
        for index in failing:
            path = backgrounds.get(index)
            if path is None:
                continue
            out.append({"slide_index": index, "path": str(path), "reason": reason})
            self._mark_discarded(str(path), reason)
        return out

    def _record(
        self,
        attempts: list[Attempt],
        number: int,
        stage: PipelineStage,
        verdict: GenerationVerdict,
        reason: str,
        slides: list[int],
        started: float,
    ) -> None:
        attempt = Attempt(
            number=number,
            stage=stage,
            verdict=verdict,
            reason=reason,
            slide_indexes=slides,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        attempts.append(attempt)
        if self.session is None:
            return
        self.session.add(
            GenerationLog(
                set_id=self.set_id,
                slide_index=slides[0] if len(slides) == 1 else None,
                stage=stage,
                attempt=number,
                verdict=verdict,
                reason=reason,
                duration_ms=attempt.duration_ms,
            )
        )
        self.session.commit()

    def _persist_asset(self, **kwargs: Any) -> None:
        if self.session is None:
            return
        self.session.add(
            Asset(
                set_id=self.set_id,
                kind=kwargs["kind"],
                path=kwargs["path"],
                width=kwargs["width"],
                height=kwargs["height"],
                provider=kwargs["provider"],
                generation_prompt=kwargs["prompt"],
                seed=kwargs["seed"],
            )
        )
        self.session.commit()

    def _mark_discarded(self, path: str, reason: str) -> None:
        if self.session is None:
            return
        from sqlmodel import select

        for asset in self.session.exec(select(Asset).where(Asset.path == path)).all():
            asset.is_discarded = True
            asset.discard_reason = reason
            self.session.add(asset)
        self.session.commit()
