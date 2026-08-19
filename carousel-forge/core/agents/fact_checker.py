"""A6 FactChecker — 주장 단위 검증.

절대 규칙 #4: **출처 없는 숫자·통계·인용을 출력하지 않는다.** 팩트체크 미통과분은
파이프라인이 거부한다.

세 가지를 한다.

  1. `evidence_needed`의 주장을 **각각 독립적으로** 검증한다. 한 번에 몰아서 물으면
     모델이 앞 주장의 판정에 뒤 주장을 끌어다 맞춘다.
  2. 카피에 남아 있는 숫자·연도·통계가 **검증된 주장으로 덮이는지** 센다. 덮이지
     않는 숫자는 출처가 없는 숫자이므로 거부한다.
  3. `false`/`disputed`는 A5로 반송하고, `unverified`는 단정형을 완화하게 한다.

검색은 Anthropic 서버에서 도는 `web_search`/`web_fetch`를 쓴다. 우리 컨테이너의
아웃바운드가 막혀 있어도 검증이 가능한 이유이고, 동시에 검색 결과가 우리 쪽
네트워크 정책에 좌우되지 않는다는 뜻이기도 하다.

모델이 답에 적은 출처 URL은 **서버 검색이 실제로 열어 본 페이지 목록과 대조**한다.
대조하지 않으면 그럴듯하게 지어낸 URL이 출처로 통과한다.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from apps.api.models import FactVerdict, PipelineStage
from core.agents.base import Agent, AgentContext
from core.config import model_routing
from core.providers.llm import LLMClient, LLMError, default_client

#: 출처가 필요한 표현. 하나라도 카피에 있으면 그 슬라이드는 근거가 있어야 한다.
#:
#: 한국어 조사가 붙어도 잡히도록 숫자 뒤를 넓게 연다. 다만 슬라이드 번호처럼
#: 순수한 서수는 제외해야 하므로, 판정은 `find_claims_needing_sources`에서 한다.
_NUMBER = re.compile(
    r"""
    (?<![\w.])              # 앞이 글자·숫자·소수점이 아니고
    (
        \d{4}\s*년           # 연도
      | \d+(?:\.\d+)?\s*%    # 퍼센트
      | \d+(?:,\d{3})+       # 천 단위 구분이 있는 큰 수
      | \d+(?:\.\d+)?\s*(?:배|만|억|조|명|건|위|퍼센트|점|시간|분|초|일|주|개월|년)
    )
    """,
    re.VERBOSE,
)

#: 인용 표시. 따옴표 안의 문장은 누가 말했는지가 필요하다.
_QUOTE = re.compile(r'[“"]([^”"]{8,})[”"]')

#: 카피에서 숫자를 세되 무시할 것들 — 슬라이드 번호, 목록 번호 같은 구조 요소.
_STRUCTURAL_ROLES = {"badge", "page_number"}


class FactCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class Source:
    title: str
    url: str

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")


@dataclass
class ClaimCheck:
    claim: str
    verdict: FactVerdict
    reasoning: str
    sources: list[Source] = field(default_factory=list)
    #: 모델이 적었지만 검색이 실제로 열어 보지 않은 URL. 지어낸 출처의 신호다.
    unverified_urls: list[str] = field(default_factory=list)
    slide_index: int | None = None

    @property
    def blocks_publication(self) -> bool:
        return self.verdict in (FactVerdict.FALSE, FactVerdict.DISPUTED)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "verdict": str(self.verdict),
            "reasoning": self.reasoning,
            "sources": [{"title": s.title, "url": s.url} for s in self.sources],
            "unverified_urls": self.unverified_urls,
            "slide_index": self.slide_index,
        }


@dataclass
class UnsourcedNumber:
    slide_index: int
    block_id: str
    text: str
    found: str

    def __str__(self) -> str:
        return (
            f"슬라이드 {self.slide_index} {self.block_id}: {self.found!r}에 대응하는 "
            f"검증된 출처가 없다 — {self.text[:60]}"
        )


@dataclass
class FactReport:
    claims: list[ClaimCheck] = field(default_factory=list)
    unsourced: list[UnsourcedNumber] = field(default_factory=list)
    searched: bool = True

    @property
    def blocking(self) -> list[ClaimCheck]:
        return [c for c in self.claims if c.blocks_publication]

    @property
    def needs_softening(self) -> list[ClaimCheck]:
        return [c for c in self.claims if c.verdict is FactVerdict.UNVERIFIED]

    @property
    def passed(self) -> bool:
        """거짓·논란 주장이 없고, 출처 없는 숫자도 없어야 통과다."""
        return not self.blocking and not self.unsourced

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "searched": self.searched,
            "claims": [c.as_dict() for c in self.claims],
            "unsourced_numbers": [
                {"slide_index": u.slide_index, "block_id": u.block_id, "found": u.found}
                for u in self.unsourced
            ],
        }

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for check in self.claims:
            counts[str(check.verdict)] = counts.get(str(check.verdict), 0) + 1
        lines = [
            f"팩트체크: {'통과' if self.passed else '거부'} "
            f"(주장 {len(self.claims)}건 · " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ")"
        ]
        for check in self.blocking:
            lines.append(f"  ✗ [{check.verdict}] {check.claim}")
            lines.append(f"     {check.reasoning[:150]}")
        for check in self.needs_softening:
            lines.append(f"  ! [unverified] {check.claim} — 단정형을 완화하거나 삭제해야 한다")
        for number in self.unsourced:
            lines.append(f"  ✗ {number}")
        if self.passed and not self.needs_softening:
            lines.append("  걸린 항목 없음")
        return "\n".join(lines)

    def markdown(self) -> str:
        """내보내기의 04_reference/fact_report.md."""
        lines = [
            "# 팩트체크 보고서",
            "",
            f"판정: **{'통과' if self.passed else '거부'}** · 검증한 주장 {len(self.claims)}건",
            "",
        ]
        for check in self.claims:
            mark = {"verified": "✅", "unverified": "⚠️", "disputed": "⛔", "false": "❌"}[
                str(check.verdict)
            ]
            lines += [f"## {mark} {check.claim}", "", check.reasoning, ""]
            if check.sources:
                lines.append("출처:")
                lines += [f"- [{s.title or s.domain}]({s.url})" for s in check.sources]
            else:
                lines.append("출처: **없음**")
            if check.unverified_urls:
                lines.append("")
                lines.append(
                    "> 아래 URL은 모델이 적었지만 검색이 실제로 열어 본 페이지가 아니다. "
                    "출처로 세지 않았다."
                )
                lines += [f"> - {u}" for u in check.unverified_urls]
            lines.append("")

        if self.unsourced:
            lines += ["## 출처 없는 숫자", ""]
            lines += [f"- {u}" for u in self.unsourced]
            lines.append("")
        return "\n".join(lines)


class ClaimVerdict(BaseModel):
    """한 주장에 대한 판정. 모델이 채운다."""

    verdict: str = Field(
        description=(
            "verified: 신뢰할 만한 출처가 주장을 직접 뒷받침한다 / "
            "unverified: 확인할 근거를 못 찾았다 / "
            "disputed: 출처마다 말이 다르다 / "
            "false: 출처가 주장을 반박한다"
        )
    )
    reasoning: str = Field(
        description="판정 근거. 어느 출처가 무엇을 말했는지 구체적으로. 애매하면 애매하다고 적어라."
    )
    source_urls: list[str] = Field(
        description="판정의 근거가 된 URL. 실제로 열어 본 것만 적어라. 없으면 빈 목록."
    )


_SYSTEM = """너는 게시 직전 원고의 사실관계를 확인하는 팩트체커다.

**근거를 못 찾은 것은 unverified다.** 그럴듯해 보인다는 이유로 verified를 주지 마라.
검증되지 않은 주장이 통과하면 그대로 게시되고, 틀린 숫자는 계정 신뢰를 무너뜨린다.

- 반드시 web_search로 **직접 찾아본 뒤** 판정해라. 기억에 의존하지 마라.
- source_urls에는 **검색으로 실제 열어 본 URL만** 적어라. 기억나는 주소를 쓰지 마라.
- 1차 출처(공식 문서, 발표, 통계기관)를 2차 인용보다 우선한다.
- 시점이 중요한 주장(가격, 정책, 규격)은 출처의 날짜를 확인하고 reasoning에 적어라.
- 출처끼리 말이 다르면 verified가 아니라 disputed다.
"""


class FactChecker(Agent):
    name = "A6 FactChecker"
    stage = PipelineStage.FACTCHECK
    milestone = "M5"

    def __init__(self, llm: LLMClient | None = None, *, max_parallel: int | None = None) -> None:
        self._llm = llm
        self.max_parallel = max_parallel or int(
            model_routing()["research"].get("parallelism", 6)
        )

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = default_client("reasoning")
        return self._llm

    def run(self, state: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        report = self.check(
            claims=state["topic"].get("evidence_needed", []),
            copy=state.get("copy"),
            ctx=ctx,
        )
        return {**state, "fact_report": report.as_dict()}

    def check(
        self,
        *,
        claims: list[str],
        copy: dict[str, Any] | None,
        ctx: AgentContext,
    ) -> FactReport:
        checks = self.verify_claims(claims, ctx) if claims else []
        unsourced = (
            find_unsourced_numbers(copy, checks) if copy is not None else []
        )
        return FactReport(claims=checks, unsourced=unsourced)

    def verify_claims(self, claims: list[str], ctx: AgentContext) -> list[ClaimCheck]:
        """주장을 **병렬로, 각각 독립적으로** 검증한다.

        한 번의 호출에 여러 주장을 넣으면 모델이 앞 판정에 뒤 판정을 맞춘다.
        하나씩 따로 물어야 서로 오염되지 않는다.
        """
        if not claims:
            return []
        workers = min(self.max_parallel, len(claims))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(lambda c: self._verify_one(c, ctx), claims))

    def _verify_one(self, claim: str, ctx: AgentContext) -> ClaimCheck:
        try:
            result = self.llm.structured(
                system=_SYSTEM,
                user=(
                    f"다음 주장을 검증해라.\n\n주장: {claim}\n\n"
                    f"맥락: {ctx.language} 사용자를 위한 콘텐츠이며 플랫폼은 {ctx.platform}다.\n"
                    "웹에서 직접 찾아보고 판정해라."
                ),
                output_model=ClaimVerdict,
                profile="reasoning",
                search=True,
            )
        except LLMError as exc:
            # 검증하지 못한 것을 verified로 넘기지 않는다.
            return ClaimCheck(
                claim=claim,
                verdict=FactVerdict.UNVERIFIED,
                reasoning=f"검증을 수행하지 못했다: {exc}",
            )

        verdict = _parse_verdict(result.parsed.verdict)
        opened = {hit.url for hit in result.search_hits}
        sources, invented = _split_sources(result.parsed.source_urls, result.search_hits)

        # 출처 없이 verified는 성립하지 않는다.
        if verdict is FactVerdict.VERIFIED and not sources:
            verdict = FactVerdict.UNVERIFIED
            note = (
                "\n\n[자동 강등] verified로 판정됐으나 검색이 실제로 열어 본 출처가 "
                "하나도 없어 unverified로 내렸다."
            )
        elif verdict is FactVerdict.VERIFIED and not opened:
            verdict = FactVerdict.UNVERIFIED
            note = "\n\n[자동 강등] 검색이 한 번도 실행되지 않아 unverified로 내렸다."
        else:
            note = ""

        return ClaimCheck(
            claim=claim,
            verdict=verdict,
            reasoning=result.parsed.reasoning + note,
            sources=sources,
            unverified_urls=invented,
        )


def _parse_verdict(value: str) -> FactVerdict:
    normalised = value.strip().lower()
    try:
        return FactVerdict(normalised)
    except ValueError:
        # 모르는 판정을 통과로 해석하지 않는다.
        return FactVerdict.UNVERIFIED


def _split_sources(
    urls: list[str], hits: list[Any]
) -> tuple[list[Source], list[str]]:
    """모델이 적은 URL을 **검색이 실제로 연 페이지**와 대조해 갈라낸다."""
    by_url = {hit.url: hit for hit in hits}
    by_domain: dict[str, Any] = {}
    for hit in hits:
        by_domain.setdefault(urlparse(hit.url).netloc.lower().removeprefix("www."), hit)

    sources: list[Source] = []
    invented: list[str] = []
    for url in urls:
        hit = by_url.get(url)
        if hit is not None:
            sources.append(Source(title=hit.title, url=hit.url))
            continue
        # 같은 도메인을 열어 봤다면 그 페이지를 근거로 인정한다 — 모델이 검색
        # 결과에서 본 사이트의 다른 경로를 적는 경우가 흔하다.
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        if domain and domain in by_domain:
            sources.append(Source(title=by_domain[domain].title, url=url))
        else:
            invented.append(url)
    return sources, invented


def find_claims_needing_sources(text: str) -> list[str]:
    """이 문장에서 출처가 필요한 표현을 찾는다. 순수 함수."""
    found = [m.group(1).strip() for m in _NUMBER.finditer(text)]
    found += [m.group(1).strip() for m in _QUOTE.finditer(text)]
    return found


def find_unsourced_numbers(
    copy: dict[str, Any], checks: list[ClaimCheck]
) -> list[UnsourcedNumber]:
    """카피의 숫자·인용이 검증된 주장으로 덮이는지 센다.

    절대 규칙 #4를 강제하는 지점이다. "이 숫자가 어느 검증된 주장에서 왔는가"에
    답할 수 없으면 그 숫자는 출처가 없는 숫자다.
    """
    verified_text = " ".join(
        check.claim + " " + check.reasoning
        for check in checks
        if check.verdict is FactVerdict.VERIFIED
    )

    out: list[UnsourcedNumber] = []
    for slide in copy.get("slides", []):
        for block in slide.get("copy_blocks", []):
            if block.get("role") in _STRUCTURAL_ROLES:
                continue  # 슬라이드 번호·라벨은 사실 주장이 아니다
            text = block.get("text", "")
            for found in find_claims_needing_sources(text):
                # 숫자 부분만 뽑아 검증된 주장 안에 같은 수가 있는지 본다.
                digits = re.sub(r"[^\d.]", "", found)
                if digits and digits in re.sub(r"[^\d.\s]", " ", verified_text):
                    continue
                if not digits and found[:20] in verified_text:
                    continue
                out.append(
                    UnsourcedNumber(
                        slide_index=slide["index"],
                        block_id=block["id"],
                        text=text,
                        found=found,
                    )
                )
    return out
