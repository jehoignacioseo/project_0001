"""이미지 생성 프로바이더 인터페이스.

**텍스트가 없는 배경만 생성한다.** 프롬프트에 텍스트 렌더링을 요청하지 않는다
(절대 규칙 #5). 네거티브 프롬프트는 config/models.yaml의
`image.negative_prompt_always`가 항상 합쳐진다.
"""

from __future__ import annotations

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
        lowered = prompt.lower()
        for marker in _TEXT_REQUEST_MARKERS:
            if marker in lowered:
                raise TextInPromptError(
                    f"배경 프롬프트에 텍스트 요청이 있다: {marker!r}. "
                    "글자는 항상 렌더 레이어(core.render)에서 처리한다."
                )
