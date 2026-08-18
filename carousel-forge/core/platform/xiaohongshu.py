"""小红书 — 정보 밀도 우선. 커버에 제목+부제+뱃지까지 싣고, 제목은 20자 안에서 승부한다."""

from __future__ import annotations

from core.platform.base import CaptionCheck, PlatformAdapter


class XiaohongshuAdapter(PlatformAdapter):
    key = "xiaohongshu"

    def assemble_caption(self, hook: str, body: str, cta: str, hashtags: list[str]) -> str:
        tags = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
        return f"{hook}\n{body}\n\n{cta}\n{tags}".strip()

    def check_cover_title(self, title: str) -> CaptionCheck:
        """제목 20자 제한 — 커버 카피 설계의 핵심 제약."""
        limit = self.spec.title_max_chars
        if limit is None:
            return CaptionCheck(ok=True, problems=[])
        if len(title) > limit:
            return CaptionCheck(
                ok=False,
                problems=[f"커버 제목이 {len(title)}자다. {limit}자를 넘으면 피드에서 잘린다"],
            )
        return CaptionCheck(ok=True, problems=[])
