"""플랫폼 어댑터 공통 인터페이스.

규격 수치는 전부 `config/platforms.yaml`에서 온다. 어댑터가 담는 것은
수치가 아니라 **규칙과 문화**다 (캡션 조립 방식, 커버 정보 밀도 등).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import PlatformSpec, platform_spec


@dataclass(frozen=True)
class CaptionCheck:
    ok: bool
    problems: list[str]


class PlatformAdapter:
    key: str = ""

    def __init__(self) -> None:
        if not self.key:
            raise ValueError("PlatformAdapter.key를 정의하라")
        self.spec: PlatformSpec = platform_spec(self.key)

    # ── 캡션 ────────────────────────────────────────────────────────────
    def assemble_caption(self, hook: str, body: str, cta: str, hashtags: list[str]) -> str:
        raise NotImplementedError

    def check_caption(self, caption: str, hashtags: list[str]) -> CaptionCheck:
        problems: list[str] = []
        if len(caption) > self.spec.caption_max_chars:
            problems.append(
                f"캡션이 {len(caption)}자로 상한 {self.spec.caption_max_chars}자를 넘는다"
            )
        if len(hashtags) > self.spec.hashtag_max:
            problems.append(
                f"해시태그 {len(hashtags)}개는 상한 {self.spec.hashtag_max}개를 넘는다"
            )
        return CaptionCheck(ok=not problems, problems=problems)

    # ── 슬라이드 ────────────────────────────────────────────────────────
    def check_slide_count(self, count: int) -> CaptionCheck:
        problems: list[str] = []
        if count > self.spec.max_slides:
            problems.append(f"슬라이드 {count}장은 상한 {self.spec.max_slides}장을 넘는다")
        if count < self.spec.min_slides:
            problems.append(f"슬라이드 {count}장은 하한 {self.spec.min_slides}장 미만이다")
        return CaptionCheck(ok=not problems, problems=problems)


def adapter_for(platform: str) -> PlatformAdapter:
    from core.platform.instagram import InstagramAdapter
    from core.platform.xiaohongshu import XiaohongshuAdapter

    adapters: dict[str, type[PlatformAdapter]] = {
        InstagramAdapter.key: InstagramAdapter,
        XiaohongshuAdapter.key: XiaohongshuAdapter,
    }
    if platform not in adapters:
        raise ValueError(f"어댑터가 없는 플랫폼: {platform}")
    return adapters[platform]()
