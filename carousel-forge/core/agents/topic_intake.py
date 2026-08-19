"""A2 TopicIntake — 어떤 입력이 와도 하나의 TopicSchema로 수렴시킨다.

| 입력 타입 | 처리 |
|---|---|
| 문서 (docx/pdf/md/txt) | 파싱 → 핵심 주장 추출 → 캐러셀 단위로 재구성 |
| 채팅 대화 | 의도·제약·톤 추출. 부족한 슬롯은 **질문 1개만** 되묻는다 |
| 키워드 1~3개 | 각도(angle) 3개 제안 → 사용자 선택 |
| URL | 페치 → 요약 → 각도 제안 |
| 시스템 제안 | A3 결과를 그대로 승계 |

`source_fidelity: strict`이면 원문에 없는 사실을 창작하지 않는다. 문서 입력의
기본값은 strict다 (절대 규칙 #4와 이어진다 — 없는 사실을 지어내면 팩트체크가
막을 방법이 없다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from apps.api.models import PipelineStage, TopicInputType
from apps.api.schemas.generated.topic import TopicBriefPayload
from core.agents.base import Agent, AgentContext
from core.config import platform_spec
from core.providers.llm import LLMClient, default_client


class NeedsUserInput(RuntimeError):
    """슬롯이 비어 진행할 수 없다. 질문은 **한 개만** 던진다."""

    def __init__(self, question: str) -> None:
        self.question = question
        super().__init__(question)


class Angle(BaseModel):
    """키워드를 자를 수 있는 한 가지 각도."""

    title: str = Field(description="이 각도로 갔을 때의 제목안")
    angle: str = Field(description="주제를 어느 각도로 자르는가")
    why_now: str = Field(description="왜 지금 이 각도인가")
    audience: str = Field(description="누가 이걸 저장하는가")
    expected_slides: int = Field(ge=3, le=20)


class AngleProposals(BaseModel):
    angles: list[Angle] = Field(min_length=3, max_length=3)


class ChatExtraction(BaseModel):
    """채팅에서 뽑아낸 것 + 아직 모르는 것."""

    topic: TopicBriefPayload | None = None
    missing_slot: str | None = Field(
        default=None, description="진행에 꼭 필요한데 대화에 없는 정보 하나"
    )
    question: str | None = Field(
        default=None, description="그 슬롯을 채우기 위해 던질 질문. 반드시 한 개."
    )


_SYSTEM = """너는 캐러셀 콘텐츠의 주제를 정리하는 편집자다.

지켜야 할 것:
- supporting_points는 3~7개. 각각이 슬라이드 한 장이 될 만큼 독립적이어야 한다.
- evidence_needed에는 숫자·통계·연도·인용처럼 **출처가 필요한 주장**만 적는다.
  나중에 팩트체커가 이 목록을 하나씩 검증하고, 검증되지 않으면 그 카피는 폐기된다.
  그러니 확인 없이 단정할 수 없는 것을 빠짐없이 적어라.
- key_message는 독자가 단 하나만 기억한다면 무엇인가에 답한다.
- source_fidelity가 strict면 주어진 원문에 없는 사실을 새로 만들지 마라.
"""


class TopicIntake(Agent):
    name = "A2 TopicIntake"
    stage = PipelineStage.INTAKE
    milestone = "M2"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("reasoning")
        return self._llm

    # ── 진입점 ──────────────────────────────────────────────────────────
    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        input_type = TopicInputType(state["input_type"])
        payload = state.get("payload")

        if input_type is TopicInputType.KEYWORD:
            topic = self._from_keywords(
                payload, ctx,
                selected=state.get("selected_angle_index"),
                out=state,
            )
        elif input_type is TopicInputType.CHAT:
            topic = self._from_chat(payload, ctx)
        elif input_type is TopicInputType.DOCUMENT:
            topic = self._from_document(payload, ctx)
        elif input_type is TopicInputType.PROPOSED:
            raise NotImplementedError(
                "시스템 제안(A3 TrendScout) 승계는 M5에서 구현된다."
            )
        else:  # pragma: no cover - enum이 막아 준다
            raise ValueError(f"알 수 없는 입력 타입: {input_type}")

        return {**state, "topic": topic.model_dump()}

    # ── 키워드 ──────────────────────────────────────────────────────────
    def propose_angles(self, keywords: list[str], ctx: AgentContext) -> AngleProposals:
        spec = platform_spec(ctx.platform)
        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"키워드: {', '.join(keywords)}\n"
                f"플랫폼: {spec.display_name} · 언어: {ctx.language}\n"
                f"플랫폼 문화: {spec.culture_prompt}\n\n"
                "이 키워드를 자를 수 있는 **서로 확연히 다른** 각도 3개를 제안해라.\n"
                "세 개가 사실상 같은 이야기면 실패한 것이다. 대상 독자나 접근 방식이 달라야 한다."
            ),
            output_model=AngleProposals,
            profile="reasoning",
        )
        return result.parsed

    def _from_keywords(
        self,
        keywords: list[str],
        ctx: AgentContext,
        *,
        selected: int | None,
        out: dict[str, Any],
    ) -> TopicBriefPayload:
        proposals = self.propose_angles(keywords, ctx)
        # 제안을 상태에 남긴다. 사용자가 나중에 다른 각도로 다시 뽑을 수 있어야 한다.
        out["angle_proposals"] = proposals.model_dump()

        if selected is None:
            # 자동 선택은 사용자 선택의 대체물이 아니라 기본값이다. 어느 것을
            # 골랐는지 상태에 남겨 나중에 바꿔 돌릴 수 있게 한다.
            selected = 0
            out["angle_auto_selected"] = True
        if not 0 <= selected < len(proposals.angles):
            raise ValueError(f"각도 인덱스가 범위를 벗어났다: {selected}")
        out["selected_angle_index"] = selected

        angle = proposals.angles[selected]
        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"키워드: {', '.join(keywords)}\n"
                f"선택된 각도: {angle.angle}\n"
                f"제목안: {angle.title}\n"
                f"독자: {angle.audience}\n"
                f"왜 지금: {angle.why_now}\n\n"
                "이 각도로 캐러셀 한 편을 만들 수 있게 주제를 정리해라.\n"
                "키워드에서 출발했으므로 source_fidelity는 flexible이다."
            ),
            output_model=TopicBriefPayload,
            profile="reasoning",
        )
        return result.parsed

    # ── 채팅 ────────────────────────────────────────────────────────────
    def _from_chat(self, transcript: str, ctx: AgentContext) -> TopicBriefPayload:
        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"플랫폼: {ctx.platform} · 언어: {ctx.language}\n\n"
                "아래 대화에서 의도·제약·톤을 뽑아 주제를 정리해라.\n"
                "정리에 꼭 필요한 정보가 대화에 **없을 때만** missing_slot과 question을 채워라. "
                "질문은 한 개만 만든다. 추측으로 채울 수 있는 것은 채우고 묻지 마라.\n\n"
                f"--- 대화 ---\n{transcript}"
            ),
            output_model=ChatExtraction,
            profile="reasoning",
        )
        extraction = result.parsed
        if extraction.topic is None:
            question = extraction.question or "이 주제로 무엇을 전하고 싶으신가요?"
            raise NeedsUserInput(question)
        return extraction.topic

    # ── 문서 ────────────────────────────────────────────────────────────
    def _from_document(self, source: Any, ctx: AgentContext) -> TopicBriefPayload:
        text = source if isinstance(source, str) and "\n" in source else None
        if text is None:
            text = read_document(Path(source))

        result = self.llm.structured(
            system=_SYSTEM,
            user=(
                f"플랫폼: {ctx.platform} · 언어: {ctx.language}\n\n"
                "아래 문서를 캐러셀로 만들 수 있게 정리해라.\n"
                "**source_fidelity는 strict다. 원문에 없는 사실을 새로 만들지 마라.** "
                "원문이 근거를 대지 않은 주장은 evidence_needed에 올려라.\n\n"
                f"--- 문서 ---\n{text[:40000]}"
            ),
            output_model=TopicBriefPayload,
            profile="reasoning",
        )
        topic = result.parsed
        # 문서 입력의 기본값은 strict다. 모델이 flexible로 답했더라도 되돌린다.
        return topic.model_copy(update={"source_fidelity": "strict"})


def read_document(path: Path) -> str:
    """문서에서 텍스트를 뽑는다. 지원하지 않는 형식이면 조용히 넘어가지 않는다."""
    suffix = path.suffix.lower()
    if not path.exists():
        raise FileNotFoundError(f"문서를 찾을 수 없다: {path}")

    if suffix in (".md", ".txt", ".markdown"):
        return path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, indent=2)
    if suffix == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    raise ValueError(
        f"지원하지 않는 문서 형식: {suffix}. 지원: .md .txt .markdown .json .docx .pdf"
    )
