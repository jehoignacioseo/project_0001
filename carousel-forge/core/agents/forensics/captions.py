"""캡션 통계 — 어미·이모지 밀도·해시태그 전략.

계정의 말투는 인상이 아니라 빈도다. 어떤 어미로 문장을 끝내는지, 이모지를 얼마나
쓰는지, 해시태그를 몇 개 어디에 붙이는지는 전부 세면 나온다. 모델에게 "말투가
어때?"라고 묻기 전에 먼저 센다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from core.agents.constraints import emoji_count, visible_length

#: 한국어 문장 종결 어미. 계정의 register(반말/존댓말/해요체)를 가르는 신호다.
#:
#: 합쇼체(-습니다/-ㅂ니다)는 여기 넣지 않는다. 한글 음절은 결합 문자라
#: "ㅂ니다"를 리터럴로 비교하면 "나옵니다"가 걸리지 않고, 그러면 반말의 "다"가
#: 대신 잡아 존댓말이 반말로 분류된다. 종성을 직접 보는 `_is_hapsyo`로 판정한다.
_ENDINGS: dict[str, tuple[str, ...]] = {
    "해요체": ("해요", "예요", "에요", "이에요", "어요", "아요", "세요", "게요", "요"),
    "존댓말": ("십시오", "습니까", "니까"),
    "반말": ("한다", "이다", "된다", "했다", "이야", "야", "지", "다"),
}

#: 한글 음절 종성 인덱스에서 'ㅂ'의 자리. (U+AC00 기준 28개 종성 중 17번)
_JONGSEONG_B = 17
_HANGUL_BASE = 0xAC00
_HANGUL_LAST = 0xD7A3


def _is_hapsyo(tail: str) -> bool:
    """합쇼체(-습니다 / -ㅂ니다)인가.

    "…니다"로 끝나면서 바로 앞 음절의 종성이 'ㅂ'이면 합쇼체다. 이 조건 하나로
    습니다·옵니다·냅니다·됩니다가 모두 걸리고, 종성이 없는 "아니다"는 걸리지 않는다.
    """
    if not tail.endswith("니다") or len(tail) < 3:
        return False
    stem = tail[-3]
    if not (_HANGUL_BASE <= ord(stem) <= _HANGUL_LAST):
        return False
    return (ord(stem) - _HANGUL_BASE) % 28 == _JONGSEONG_B

_HASHTAG_RE = re.compile(r"#[^\s#]+")
_SENTENCE_SPLIT = re.compile(r"[.!?。\n]+")


@dataclass
class CaptionStats:
    """캡션 묶음에서 센 값들. StyleDNA의 copy·caption 블록으로 그대로 옮겨진다."""

    sample_count: int
    register: str
    register_confidence: float
    sentence_length_avg: float
    emoji_density: float
    emoji_palette: tuple[str, ...]
    hashtag_count_avg: float
    hashtag_placement: str
    caption_length_range: tuple[int, int]
    first_line_length_avg: float
    punctuation_habits: str
    repeated_phrases: tuple[str, ...] = field(default_factory=tuple)

    def as_dna_fragments(self) -> dict[str, dict]:
        """StyleDNA의 copy / caption 블록에 넣을 조각."""
        return {
            "copy": {
                "register": self.register,
                "sentence_length_avg": round(self.sentence_length_avg, 1),
                "emoji_density": round(self.emoji_density, 4),
                "emoji_palette": list(self.emoji_palette),
                "punctuation_habits": self.punctuation_habits,
            },
            "caption": {
                "length_range": list(self.caption_length_range),
                "hashtag_count": round(self.hashtag_count_avg),
                "placement": self.hashtag_placement,
            },
        }


#: 1·2위 표차가 이 비율 안이면 하나로 단정하지 않고 혼용으로 본다.
MIXED_REGISTER_MARGIN = 0.25


def _detect_register(sentences: list[str]) -> tuple[str, float]:
    """문장 끝을 세어 말투를 정한다.

    표가 갈리면 억지로 하나를 고르지 않는다. 실제 계정은 존댓말과 해요체를
    섞어 쓰는 경우가 흔하고, 그걸 "존댓말"로 단정하면 카피 생성 단계에서
    원본과 다른 말투가 나온다. 혼용은 혼용이라고 적는 편이 정확하다.
    """
    votes: Counter[str] = Counter()
    for sentence in sentences:
        tail = sentence.rstrip().rstrip("~…").strip()
        if not tail:
            continue
        if _is_hapsyo(tail):
            votes["존댓말"] += 1
            continue
        for register, endings in _ENDINGS.items():
            # 긴 어미부터 검사해야 "해요"가 "요"에 먹히지 않는다.
            if any(tail.endswith(e) for e in sorted(endings, key=len, reverse=True)):
                votes[register] += 1
                break
    if not votes:
        return "판정 불가 (샘플에 종결 어미가 없다)", 0.0

    total = sum(votes.values())
    ranked = votes.most_common()
    top, count = ranked[0]
    share = count / total

    if len(ranked) > 1:
        runner, runner_count = ranked[1]
        if (count - runner_count) / total <= MIXED_REGISTER_MARGIN:
            pair = " · ".join(sorted((top, runner)))
            return f"{pair} 혼용", (count + runner_count) / total

    return top, share


def _punctuation_habits(captions: list[str]) -> str:
    joined = "".join(captions)
    total = max(len(joined), 1)
    notes = []
    if joined.count("!") / total > 0.004:
        notes.append("느낌표를 자주 쓴다")
    elif "!" not in joined:
        notes.append("느낌표를 쓰지 않는다")
    if joined.count("…") + joined.count("...") > len(captions):
        notes.append("말줄임표로 호흡을 만든다")
    breaks_per_caption = sum(c.count("\n") for c in captions) / max(len(captions), 1)
    if breaks_per_caption >= 4:
        notes.append("줄바꿈을 많이 써서 문장을 잘게 끊는다")
    elif breaks_per_caption < 1:
        notes.append("줄바꿈 없이 한 덩어리로 쓴다")
    if "?" in joined:
        notes.append("질문형 문장을 섞는다")
    return ". ".join(notes) if notes else "특별한 습관이 관찰되지 않는다"


def _repeated_phrases(captions: list[str], *, min_len: int = 3, top: int = 5) -> tuple[str, ...]:
    """여러 캡션에 반복 등장하는 짧은 구문 — signature_phrases 후보."""
    counts: Counter[str] = Counter()
    for caption in captions:
        words = re.findall(r"[가-힣A-Za-z0-9]+", caption)
        seen_here = set()
        for size in (2, 3):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i : i + size])
                if len(phrase) >= min_len and phrase not in seen_here:
                    seen_here.add(phrase)
                    counts[phrase] += 1
    # 캡션 절반 이상에 나오는 구문만 시그니처로 본다.
    threshold = max(2, len(captions) // 2)
    return tuple(p for p, c in counts.most_common(top * 3) if c >= threshold)[:top]


def analyse_captions(captions: list[str]) -> CaptionStats:
    if not captions:
        raise ValueError("분석할 캡션이 없다")

    bodies, hashtags_per_caption, placements = [], [], []
    for caption in captions:
        tags = _HASHTAG_RE.findall(caption)
        hashtags_per_caption.append(len(tags))
        body = _HASHTAG_RE.sub("", caption).strip()
        bodies.append(body)
        if not tags:
            placements.append("none")
        else:
            # 태그가 캡션 끝쪽에 몰려 있으면 end, 본문에 흩어져 있으면 inline.
            last_body_char = max((caption.rfind(ch) for ch in body[-10:] if ch), default=0)
            first_tag = caption.find(tags[0])
            placements.append("end" if first_tag >= last_body_char else "inline")

    sentences = [s.strip() for body in bodies for s in _SENTENCE_SPLIT.split(body) if s.strip()]
    register, confidence = _detect_register(sentences)

    total_chars = sum(visible_length(b) for b in bodies)
    total_emoji = sum(emoji_count(c) for c in captions)
    emoji_chars = [ch for c in captions for ch in c if emoji_count(ch)]

    lengths = [visible_length(c) for c in captions]
    first_lines = [visible_length(c.split("\n", 1)[0]) for c in captions]

    placement_votes = Counter(p for p in placements if p != "none")
    placement = placement_votes.most_common(1)[0][0] if placement_votes else "end"

    return CaptionStats(
        sample_count=len(captions),
        register=register,
        register_confidence=confidence,
        sentence_length_avg=(
            sum(visible_length(s) for s in sentences) / len(sentences) if sentences else 0.0
        ),
        emoji_density=total_emoji / max(total_chars, 1),
        emoji_palette=tuple(p for p, _ in Counter(emoji_chars).most_common(8)),
        hashtag_count_avg=sum(hashtags_per_caption) / len(captions),
        hashtag_placement=placement,
        caption_length_range=(min(lengths), max(lengths)),
        first_line_length_avg=sum(first_lines) / len(first_lines),
        punctuation_habits=_punctuation_habits(captions),
        repeated_phrases=_repeated_phrases(captions),
    )
