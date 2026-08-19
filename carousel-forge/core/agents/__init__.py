"""A1~A10 에이전트.

구현됨: A2 TopicIntake · A4 NarrativeArchitect · A5 CopySmith (M2).
나머지는 계약(클래스·단계·마일스톤)만 있고 `run`은 NotImplementedError를 낸다.
미구현을 빈 결과로 감추지 않는다.

주의 — 상태 머신 순서와 마일스톤 순서는 다르다. 파이프라인은
INTAKE → STYLE_RESOLVE → RESEARCH → FACTCHECK → ARCHITECT → COPY 순인데,
그 사이의 A1(M3)·A3/A6(M5)이 아직 없다. 그래서 M2 산출물은 전체 오케스트레이터가
아니라 세 에이전트를 직접 이어 붙여 확인한다 (`scripts/demo_m2.py`).
"""

from .art_director import ArtDirectionError, ArtDirector, build_prompt
from .base import Agent, AgentContext
from .constraints import CopyConstraints, Violation
from .copysmith import CopyError, CopySmith
from .fact_checker import (
    ClaimCheck,
    FactChecker,
    FactCheckError,
    FactReport,
    find_claims_needing_sources,
    find_unsourced_numbers,
)
from .layout_compositor import (
    CompositionError,
    LayoutCompositor,
    NeedsNewBackground,
    NeedsShorterCopy,
)
from .localizer import Localizer
from .narrative_architect import NarrativeArchitect, OutlineError, check_outline
from .quality_gate import (
    Judgement,
    QualityGate,
    QualityGateError,
    QualityReport,
    verdict_for,
)
from .style_forensics import ForensicsError, ForensicsResult, StyleForensics
from .topic_intake import NeedsUserInput, TopicIntake
from .trend_scout import TrendScout

__all__ = [
    "Agent",
    "AgentContext",
    "ArtDirectionError",
    "ArtDirector",
    "CompositionError",
    "CopyConstraints",
    "CopyError",
    "CopySmith",
    "ClaimCheck",
    "FactCheckError",
    "FactChecker",
    "FactReport",
    "LayoutCompositor",
    "NeedsNewBackground",
    "NeedsShorterCopy",
    "Localizer",
    "NarrativeArchitect",
    "NeedsUserInput",
    "OutlineError",
    "Judgement",
    "QualityGate",
    "QualityGateError",
    "QualityReport",
    "ForensicsError",
    "ForensicsResult",
    "StyleForensics",
    "TopicIntake",
    "TrendScout",
    "Violation",
    "build_prompt",
    "check_outline",
    "find_claims_needing_sources",
    "find_unsourced_numbers",
    "verdict_for",
]
