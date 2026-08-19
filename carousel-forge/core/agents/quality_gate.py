"""A9 QualityGate — 폐기·재생성 결정권자.

절대 규칙 #6: **품질 미달을 통과시키지 않는다.** "완료"는 성공이 아니다.
기준 미달이면 폐기·재생성하고, 재시도가 소진되면 명시적으로 실패를 보고한다.

`config/quality_rules.yaml`의 blocking 항목이 **하나라도** FAIL이면 세트는
통과하지 못한다. 판정마다 구체적인 사유를 남긴다 — "품질이 낮음" 같은 문장은
남기지 않는다. 나중에 무엇을 고쳐야 하는지 알 수 없기 때문이다.

판정 방식은 셋으로 나뉜다.
  geometric — 실측 좌표·픽셀에서 센다 (text_overflow, contrast_below_wcag)
  rule      — 데이터끼리 대조한다 (factcheck_false, style_deviation)
  vision    — 비전 모델이 본다 (AI 티, 손가락, 정체성 흔들림, 플라스틱 피부)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from apps.api.models import GenerationVerdict, PipelineStage
from core.agents.base import Agent, AgentContext
from core.agents.forensics import compare_dna
from core.config import quality_rules
from core.render.geometry import failing_contrast, find_overflows
from core.render.html_renderer import SlideMeasurement
from core.providers.llm import LLMClient, default_client


class QualityGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Judgement:
    """규칙 하나에 대한 판정. 사유 없이 통과도 폐기도 없다."""

    rule_id: str
    passed: bool
    severity: str            # blocking | warning
    reason: str
    slide_index: int | None = None
    detector: str = "rule"

    def __str__(self) -> str:
        mark = "✓" if self.passed else ("✗" if self.severity == "blocking" else "!")
        where = f" [슬라이드 {self.slide_index}]" if self.slide_index else ""
        return f"{mark} {self.rule_id}{where}: {self.reason}"


@dataclass
class QualityReport:
    judgements: list[Judgement] = field(default_factory=list)

    @property
    def blocking_failures(self) -> list[Judgement]:
        return [j for j in self.judgements if not j.passed and j.severity == "blocking"]

    @property
    def warnings(self) -> list[Judgement]:
        return [j for j in self.judgements if not j.passed and j.severity == "warning"]

    @property
    def passed(self) -> bool:
        """blocking이 하나라도 실패하면 통과가 아니다."""
        return not self.blocking_failures

    def failing_slides(self) -> set[int]:
        return {j.slide_index for j in self.blocking_failures if j.slide_index is not None}

    def rules_failed(self) -> list[str]:
        return sorted({j.rule_id for j in self.blocking_failures})

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blocking_failures": [
                {"rule": j.rule_id, "slide": j.slide_index, "reason": j.reason}
                for j in self.blocking_failures
            ],
            "warnings": [
                {"rule": j.rule_id, "slide": j.slide_index, "reason": j.reason}
                for j in self.warnings
            ],
            "checked": len(self.judgements),
        }

    def summary(self) -> str:
        lines = [
            f"품질 게이트: {'통과' if self.passed else '폐기'} "
            f"({len(self.judgements)}개 검사)"
        ]
        for j in self.blocking_failures:
            lines.append(f"  {j}")
        for j in self.warnings:
            lines.append(f"  {j}")
        if self.passed and not self.warnings:
            lines.append("  걸린 항목 없음")
        return "\n".join(lines)


class VisionVerdict(BaseModel):
    """비전 모델의 판정. 애매하면 애매하다고 적게 한다."""

    looks_ai_generated: bool = Field(description="이 이미지가 AI 생성물로 보이는가")
    ai_text_artifact: bool = Field(description="이미지 안에 글자·워터마크·로고가 렌더링돼 있는가")
    hand_finger_anomaly: bool = Field(description="손가락 개수나 형태가 이상한가")
    plastic_skin: bool = Field(description="피부가 하이퍼스무스한가 (사람이 없으면 false)")
    morphing_artifact: bool = Field(description="구조가 녹아내리거나 왜곡된 곳이 있는가")
    reason: str = Field(description="판정 근거를 구체적으로. 어디의 무엇이 문제인지 적어라.")


class IdentityVerdict(BaseModel):
    identity_drift: bool = Field(description="슬라이드 간 인물 얼굴이 서로 다른 사람으로 보이는가")
    reason: str


_VISION_SYSTEM = """너는 업로드 직전 이미지를 검수하는 사람이다.

**애매하면 걸러라.** 통과시켰다가 어색한 결과물이 나가는 쪽이, 한 번 더 만드는
것보다 비싸다. "괜찮아 보인다"는 통과 사유가 아니다.

특히 이런 것을 본다:
- 이미지 안에 렌더링된 글자·숫자·워터마크·로고 (배경에는 글자가 없어야 한다)
- 손가락 개수·관절 방향
- 하이퍼스무스한 피부, 인공적인 광택, 과채도
- 구조가 녹아내리거나 물체가 서로 뭉개진 곳

reason에는 반드시 **어디의 무엇이** 문제인지 적어라. "AI 같다" 같은 문장은
사유가 아니다.
"""


class QualityGate(Agent):
    name = "A9 QualityGate"
    stage = PipelineStage.QUALITY_GATE
    milestone = "M4"

    def __init__(self, llm: LLMClient | None = None, *, use_vision: bool = True) -> None:
        self._llm = llm
        self.use_vision = use_vision
        self.rules = quality_rules()

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("reasoning")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        report = self.judge(
            measurements=state["measurements"],
            ctx=ctx,
            fact_report=state.get("fact_report"),
            rendered_dna=state.get("rendered_style_dna"),
        )
        return {**state, "quality_report": report.as_dict()}

    # ── 판정 ────────────────────────────────────────────────────────────
    def judge(
        self,
        *,
        measurements: list[SlideMeasurement],
        ctx: AgentContext,
        fact_report: dict[str, Any] | None = None,
        rendered_dna: dict[str, Any] | None = None,
        backgrounds: dict[int, Path] | None = None,
    ) -> QualityReport:
        blocking_ids = {r["id"] for r in self.rules["blocking"]}
        warning_ids = {r["id"] for r in self.rules["warning"]}
        judgements: list[Judgement] = []

        judgements += self._geometric(measurements, blocking_ids)
        judgements += self._rules(fact_report, rendered_dna, ctx, blocking_ids, warning_ids)
        if self.use_vision:
            judgements += self._vision(measurements, blocking_ids, backgrounds)

        report = QualityReport(judgements=judgements)
        self._assert_reasons(report)
        return report

    def _geometric(
        self, measurements: list[SlideMeasurement], blocking_ids: set[str]
    ) -> list[Judgement]:
        out: list[Judgement] = []
        for measurement in measurements:
            overflows = find_overflows(measurement)
            out.append(
                Judgement(
                    rule_id="text_overflow",
                    passed=not overflows,
                    severity="blocking",
                    slide_index=measurement.index,
                    detector="geometric",
                    reason=(
                        "모든 카피가 안전영역 안에 있다"
                        if not overflows
                        else "; ".join(str(o) for o in overflows)
                    ),
                )
            )
            if measurement.background_png_path is None:
                # 배경을 안 찍었으면 대비를 잴 수 없다. 잰 척하지 않는다.
                out.append(
                    Judgement(
                        rule_id="contrast_below_wcag",
                        passed=False,
                        severity="blocking",
                        slide_index=measurement.index,
                        detector="geometric",
                        reason=(
                            "배경 전용 이미지가 없어 대비를 측정하지 못했다. "
                            "capture_background=True로 렌더해야 판정할 수 있다."
                        ),
                    )
                )
                continue
            failures = failing_contrast(measurement)
            out.append(
                Judgement(
                    rule_id="contrast_below_wcag",
                    passed=not failures,
                    severity="blocking",
                    slide_index=measurement.index,
                    detector="geometric",
                    reason=(
                        "모든 카피가 WCAG 대비를 충족한다"
                        if not failures
                        else "; ".join(str(f) for f in failures)
                    ),
                )
            )
        return out

    def _rules(
        self,
        fact_report: dict[str, Any] | None,
        rendered_dna: dict[str, Any] | None,
        ctx: AgentContext,
        blocking_ids: set[str],
        warning_ids: set[str],
    ) -> list[Judgement]:
        out: list[Judgement] = []

        # factcheck_false — A6(M5)이 붙기 전에는 검증 자체가 없었다는 사실을 남긴다.
        if fact_report is None:
            out.append(
                Judgement(
                    rule_id="factcheck_false",
                    passed=True,
                    severity="warning",
                    reason=(
                        "팩트체크 보고서가 없다 — A6 FactChecker는 M5다. "
                        "출처가 필요한 주장이 검증되지 않은 채로 통과했다."
                    ),
                )
            )
        else:
            bad = [
                c for c in fact_report.get("claims", [])
                if c.get("verdict") in ("false", "disputed")
            ]
            out.append(
                Judgement(
                    rule_id="factcheck_false",
                    passed=not bad,
                    severity="blocking",
                    reason=(
                        "false/disputed 판정이 없다"
                        if not bad
                        else "; ".join(
                            f"{c['verdict']}: {c['claim']}" for c in bad
                        )
                    ),
                )
            )

        # style_deviation — 렌더에 실제로 쓰인 스타일이 DNA를 벗어났는가
        if rendered_dna is not None and ctx.style_dna is not None:
            comparison = compare_dna(ctx.style_dna, rendered_dna)
            drifted = [m for m in comparison.measured() if not m.ok]
            out.append(
                Judgement(
                    rule_id="style_deviation",
                    passed=not drifted,
                    severity="blocking",
                    detector="rule",
                    reason=(
                        f"DNA 대비 이탈 없음 (일치 {comparison.score:.0%})"
                        if not drifted
                        else "; ".join(
                            f"{m.field} {m.expected}→{m.actual} ({m.detail})" for m in drifted
                        )
                    ),
                )
            )
        return out

    def _vision(
        self,
        measurements: list[SlideMeasurement],
        blocking_ids: set[str],
        backgrounds: dict[int, Path] | None,
    ) -> list[Judgement]:
        out: list[Judgement] = []
        for measurement in measurements:
            # 합성본이 아니라 **배경**을 본다. 합성본의 글자는 우리가 얹은 것이라
            # "이미지 안의 글자"로 잡히면 안 된다.
            image = (backgrounds or {}).get(measurement.index) or measurement.background_png_path
            if image is None:
                continue

            verdict = self.llm.structured(
                system=_VISION_SYSTEM,
                user=(
                    "이 배경 이미지를 검수해라. 이 이미지에는 원래 글자가 없어야 한다 "
                    "— 텍스트는 나중에 별도 레이어로 얹힌다.\n"
                    "판정 근거를 구체적으로 적어라."
                ),
                output_model=VisionVerdict,
                images=[image],
                profile="reasoning",
            ).parsed

            checks = (
                ("ai_text_artifact", verdict.ai_text_artifact),
                ("hand_finger_anomaly", verdict.hand_finger_anomaly),
                ("plastic_skin", verdict.plastic_skin),
                ("morphing_artifact", verdict.morphing_artifact),
            )
            for rule_id, failed in checks:
                if rule_id not in blocking_ids:
                    continue
                out.append(
                    Judgement(
                        rule_id=rule_id,
                        passed=not failed,
                        severity="blocking",
                        slide_index=measurement.index,
                        detector="vision",
                        reason=verdict.reason,
                    )
                )
        return out

    def _assert_reasons(self, report: QualityReport) -> None:
        """사유가 비거나 너무 짧으면 판정 자체를 신뢰할 수 없다."""
        logging_rules = self.rules.get("logging", {})
        if not logging_rules.get("require_reason", True):
            return
        minimum = int(logging_rules.get("min_reason_chars", 0))
        thin = [
            j for j in report.judgements
            if not j.passed and len(j.reason.strip()) < minimum
        ]
        if thin:
            raise QualityGateError(
                "폐기 사유가 너무 짧다 — 무엇을 고쳐야 하는지 알 수 없는 판정은 "
                f"남기지 않는다: {[j.rule_id for j in thin]}"
            )


def verdict_for(report: QualityReport) -> GenerationVerdict:
    if not report.passed:
        return GenerationVerdict.DISCARD
    return GenerationVerdict.WARN if report.warnings else GenerationVerdict.PASS
