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

    def format_tag(self, tag: str) -> str:
        """플랫폼 표기로 감싼 해시태그.

        표기는 `config/platforms.yaml`의 `topic_tag_format`에서 온다. 샤오홍슈의
        话题 태그처럼 '#이름' 뒤에 꼬리표가 붙는 플랫폼이 있고, 표기가 틀리면
        태그가 일반 텍스트로 들어가 노출이 되지 않는다 (절대 규칙 #2).
        """
        name = tag.lstrip("#").strip()
        if not name:
            raise ValueError("빈 해시태그는 표기할 수 없다")
        return self.spec.topic_tag_format.replace("{tag}", name)

    # ── 슬라이드 ────────────────────────────────────────────────────────
    def check_cover_density(self, cover_blocks: list[dict]) -> CaptionCheck:
        """커버가 이 플랫폼 문화가 기대하는 만큼 정보를 싣고 있는가.

        하드 제약이 아니다 — 규격이 아니라 문화이기 때문이다. 판정을 남기는 이유는
        인스타그램 커버를 그대로 샤오홍슈로 옮기면 심심하게 읽히는데, 그 사실이
        아무 데도 안 남으면 왜 성과가 안 나오는지 알 수 없기 때문이다.
        """
        count = len([b for b in cover_blocks if (b.get("text") or "").strip()])
        if count >= self.spec.cover_min_blocks:
            return CaptionCheck(ok=True, problems=[])
        return CaptionCheck(
            ok=False,
            problems=[
                f"커버 블록이 {count}개다. {self.spec.display_name}은 커버 정보 밀도가 "
                f"'{self.spec.cover_info_density}'라 {self.spec.cover_min_blocks}개 이상을 "
                "기대한다"
            ],
        )

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
