"""이미지 생성 프로바이더 인터페이스.

**텍스트가 없는 배경만 생성한다.** 프롬프트에 텍스트 렌더링을 요청하지 않는다
(절대 규칙 #5). 네거티브 프롬프트는 config/models.yaml의
`image.negative_prompt_always`가 항상 합쳐진다.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.config import model_routing

#: 프롬프트에 들어오면 곧바로 거부할 신호들. 배경에 글자를 굽지 않기 위한 방어선.
_TEXT_REQUEST_MARKERS = (
    "text saying",
    "with the words",
    "typography",
    "caption on image",
    "글자",
    "텍스트를 넣",
    "문구를 넣",
)

#: 같은 절 안에 이런 말이 있으면 **글자를 넣지 말라는 뜻**이다.
#: 좋은 프롬프트일수록 "글자 없음", "로고는 배제"처럼 부정형으로 쓰기 때문에,
#: 부분 문자열만 보면 잘 쓴 프롬프트가 오히려 걸린다.
_NEGATION_MARKERS = (
    "없", "배제", "제외", "금지", "넣지 마", "쓰지 마", "빼고",
    "no ", "without", "avoid", "exclude", "free of", "devoid",
)

#: 절 경계. 한 문장 안에서도 "…는 배제"처럼 부정이 걸리는 단위로 쪼갠다.
_CLAUSE_SPLIT = re.compile(r"[.。;\n]+")


def find_text_requests(prompt: str) -> list[str]:
    """프롬프트가 **글자를 그려 달라고** 요구하는 지점을 찾는다.

    부정문은 요구가 아니다. "글자 없음"과 "글자를 넣어라"를 같은 것으로 취급하면
    잘 쓴 프롬프트를 막게 된다.
    """
    found: list[str] = []
    for clause in _CLAUSE_SPLIT.split(prompt):
        lowered = clause.lower()
        hits = [m for m in _TEXT_REQUEST_MARKERS if m in lowered]
        if not hits:
            continue
        if any(negation in lowered for negation in _NEGATION_MARKERS):
            continue        # 넣지 말라는 뜻이다
        found += hits
    return found


class TextInPromptError(ValueError):
    """배경 프롬프트에 텍스트 렌더링 요청이 섞였다. 글자는 렌더 레이어에서만 처리한다."""


@dataclass
class ImageRequest:
    prompt: str
    width: int
    height: int
    negative: list[str] = field(default_factory=list)
    seed: int | None = None
    identity_ref: str | None = None   # Higgsfield Soul/Element 등 정체성 고정 참조

    def full_negative(self) -> list[str]:
        always = model_routing()["image"]["negative_prompt_always"]
        return list(dict.fromkeys([*always, *self.negative]))


@dataclass
class ImageResult:
    path: str
    width: int
    height: int
    provider: str
    seed: int | None
    prompt: str


class ImageProvider(ABC):
    key: str = ""

    @abstractmethod
    def generate(self, request: ImageRequest) -> ImageResult: ...

    @staticmethod
    def assert_no_text_request(prompt: str) -> None:
        requests = find_text_requests(prompt)
        if requests:
            raise TextInPromptError(
                f"배경 프롬프트에 텍스트 요청이 있다: {requests}. "
                "글자는 항상 렌더 레이어(core.render)에서 처리한다."
            )
