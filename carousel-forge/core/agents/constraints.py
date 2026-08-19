"""StyleDNA 제약 강제.

절대 규칙 #8: 스타일 DNA를 임의로 해석하지 않는다. 팔레트·타이포·글자수는
**하드 제약**이다.

여기 있는 함수는 전부 순수 함수다. LLM이 제약을 지켰는지 판정하는 일을 모델에게
다시 맡기지 않는다 — 프롬프트에 제약을 싣는 것과, 결과가 제약을 지켰는지 세는
것은 별개의 일이고, 후자는 코드가 해야 한다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from core.config import PlatformSpec

Severity = Literal["blocking", "warning"]

#: 이모지 판정용 범위. 계정별 이모지 밀도를 세려면 "무엇이 이모지인가"를
#: 먼저 정해야 한다. 변형 선택자와 ZWJ는 개수에 넣지 않는다(한 덩어리로 센다).
_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),   # 그림문자 전반
    (0x1F000, 0x1F2FF),   # 마작·카드·괄호문자
    (0x2600, 0x27BF),     # 기타 기호·딩벳
    (0x2B00, 0x2BFF),
    (0xFE0F, 0xFE0F),     # variation selector-16 (제외 처리용)
)
_SKIP_CODEPOINTS = {0xFE0F, 0x200D}


@dataclass(frozen=True)
class Violation:
    """제약 위반 한 건. 어떤 필드가 왜 걸렸는지 구체적으로 남긴다."""

    field: str
    message: str
    severity: Severity = "blocking"

    def __str__(self) -> str:
        mark = "✗" if self.severity == "blocking" else "!"
        return f"{mark} {self.field}: {self.message}"


def emoji_count(text: str) -> int:
    """이모지 개수. ZWJ로 이어진 연속 이모지는 하나로 센다."""
    count = 0
    previous_was_emoji = False
    joined = False
    for char in text:
        code = ord(char)
        if code in _SKIP_CODEPOINTS:
            joined = code == 0x200D
            continue
        is_emoji = any(lo <= code <= hi for lo, hi in _EMOJI_RANGES if lo != 0xFE0F)
        if is_emoji and not (joined and previous_was_emoji):
            count += 1
        previous_was_emoji = is_emoji
        joined = False
    return count


def visible_length(text: str) -> int:
    """글자수 세기.

    StyleDNA의 글자수 상한은 사람이 화면에서 세는 감각을 옮긴 값이다. 그래서
    줄바꿈은 세지 않고, 결합 문자는 앞 글자에 붙여 하나로 센다.
    """
    stripped = text.replace("\n", "")
    return sum(1 for ch in stripped if not unicodedata.combining(ch))


@dataclass(frozen=True)
class CopyConstraints:
    """StyleDNA의 copy 블록을 판정 가능한 형태로 옮긴 것."""

    language: str
    register: str
    headline_char_limit: int
    body_char_limit: int
    emoji_density: float
    emoji_palette: tuple[str, ...]
    forbidden_words: tuple[str, ...]
    signature_phrases: tuple[str, ...]
    punctuation_habits: str
    #: 샤오홍슈처럼 커버 제목 글자수가 플랫폼 규격으로 잡혀 있는 경우
    cover_title_limit: int | None = None

    @classmethod
    def from_dna(cls, dna: dict[str, Any], spec: PlatformSpec) -> CopyConstraints:
        copy = dna["copy"]
        return cls(
            language=copy["language"],
            register=copy["register"],
            headline_char_limit=int(copy["headline_char_limit"]),
            body_char_limit=int(copy["body_char_limit_per_slide"]),
            emoji_density=float(copy["emoji_density"]),
            emoji_palette=tuple(copy.get("emoji_palette", [])),
            forbidden_words=tuple(copy.get("forbidden_words", [])),
            signature_phrases=tuple(copy.get("signature_phrases", [])),
            punctuation_habits=copy.get("punctuation_habits", ""),
            cover_title_limit=spec.title_max_chars,
        )

    def limit_for(self, role: str) -> int:
        """역할별 글자수 상한. 헤드라인 계열과 본문 계열의 상한이 다르다."""
        if role in ("headline", "cta"):
            return self.headline_char_limit
        if role in ("eyebrow", "badge", "page_number"):
            # 라벨류는 헤드라인의 절반 이하로 짧게 간다.
            return max(2, self.headline_char_limit // 2)
        return self.body_char_limit

    def check_text(self, text: str, *, field_name: str, role: str) -> list[Violation]:
        """카피 한 덩어리를 제약에 걸어 본다."""
        out: list[Violation] = []
        limit = self.limit_for(role)
        length = visible_length(text)
        if length > limit:
            out.append(
                Violation(
                    field_name,
                    f"{length}자로 {role} 상한 {limit}자를 {length - limit}자 넘는다",
                )
            )

        lowered = text.lower()
        for word in self.forbidden_words:
            if word.lower() in lowered:
                out.append(
                    Violation(field_name, f"금지어 {word!r}가 들어 있다")
                )

        found = emoji_count(text)
        allowed = self.emoji_density * max(length, 1)
        if found > allowed:
            detail = "이 계정은 이모지를 쓰지 않는다" if self.emoji_density == 0 else (
                f"허용치는 {length}자 기준 {allowed:.1f}개다"
            )
            out.append(Violation(field_name, f"이모지가 {found}개 있다. {detail}"))

        off_palette = [
            ch for ch in text
            if emoji_count(ch) and self.emoji_palette and ch not in self.emoji_palette
        ]
        if off_palette:
            out.append(
                Violation(
                    field_name,
                    f"팔레트 밖 이모지 {''.join(off_palette)} — 이 계정은 "
                    f"{''.join(self.emoji_palette)}만 쓴다",
                )
            )
        return out


@dataclass
class CaptionConstraints:
    """StyleDNA의 caption 블록 + 플랫폼 규격."""

    length_min: int
    length_max: int
    fold_at: int
    platform_caption_max: int
    hashtag_count: int
    hashtag_max: int

    @classmethod
    def from_dna(cls, dna: dict[str, Any], spec: PlatformSpec) -> CaptionConstraints:
        caption = dna["caption"]
        lo, hi = caption["length_range"]
        return cls(
            length_min=int(lo),
            length_max=int(hi),
            fold_at=spec.caption_fold_at,
            platform_caption_max=spec.caption_max_chars,
            hashtag_count=int(caption["hashtag_strategy"]["count"]),
            hashtag_max=spec.hashtag_max,
        )

    def check(self, hook_line: str, body: str, cta: str, hashtags: list[str]) -> list[Violation]:
        out: list[Violation] = []
        full = "\n\n".join(part for part in (hook_line, body, cta) if part)
        total = visible_length(full)

        if total > self.platform_caption_max:
            out.append(
                Violation("caption", f"{total}자로 플랫폼 상한 {self.platform_caption_max}자를 넘는다")
            )
        if not self.length_min <= total <= self.length_max:
            # 스타일 범위 이탈은 진행을 막지 않는다 — quality_rules.yaml의 warning 항목이다.
            out.append(
                Violation(
                    "caption",
                    f"{total}자는 이 계정의 캡션 길이 범위 {self.length_min}~{self.length_max}자 밖이다",
                    severity="warning",
                )
            )
        hook_len = visible_length(hook_line)
        if hook_len > self.fold_at:
            out.append(
                Violation(
                    "caption.hook_line",
                    f"{hook_len}자다. {self.fold_at}자에서 접히므로 훅이 잘린다",
                )
            )
        if len(hashtags) > self.hashtag_max:
            out.append(
                Violation("hashtags", f"{len(hashtags)}개는 플랫폼 상한 {self.hashtag_max}개를 넘는다")
            )
        if len(hashtags) != self.hashtag_count:
            out.append(
                Violation(
                    "hashtags",
                    f"{len(hashtags)}개다. 이 계정의 전략은 {self.hashtag_count}개다",
                    severity="warning",
                )
            )
        duplicates = {t for t in hashtags if hashtags.count(t) > 1}
        if duplicates:
            out.append(Violation("hashtags", f"중복된 태그: {', '.join(sorted(duplicates))}"))
        return out


def blocking(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.severity == "blocking"]


def describe(violations: list[Violation]) -> str:
    return "\n".join(f"  - {v}" for v in violations)
