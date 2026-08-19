"""小红书 — 정보 밀도 우선. 커버에 제목+부제+뱃지까지 싣고, 제목은 20자 안에서 승부한다."""

from __future__ import annotations

from core.platform.base import CaptionCheck, PlatformAdapter


class XiaohongshuAdapter(PlatformAdapter):
    key = "xiaohongshu"

    def assemble_caption(self, hook: str, body: str, cta: str, hashtags: list[str]) -> str:
        """话题 태그는 본문 끝에 플랫폼 표기로 붙인다.

        인스타그램과 달리 빈 줄을 크게 두지 않는다 — 접히는 지점이 80자라 여백이
        곧 손해다.
        """
        tags = " ".join(self.format_tag(t) for t in hashtags)
        return f"{hook}\n{body}\n\n{cta}\n{tags}".strip()

    def check_caption(self, caption: str, hashtags: list[str]) -> CaptionCheck:
        base = super().check_caption(caption, hashtags)
        problems = list(base.problems)

        first_line = caption.split("\n", 1)[0]
        if len(first_line) > self.spec.caption_fold_at:
            problems.append(
                f"첫 줄이 {len(first_line)}자다. {self.spec.caption_fold_at}자에서 접힌다"
            )
        lo, hi = self.spec.hashtag_recommended
        if hashtags and not (lo <= len(hashtags) <= hi):
            problems.append(f"话题 태그 권장 범위는 {lo}~{hi}개다 (현재 {len(hashtags)}개)")
        return CaptionCheck(ok=not problems, problems=problems)

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
