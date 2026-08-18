"""Instagram — 여백·절제·비주얼 우선. 커버는 훅 한 문장."""

from __future__ import annotations

from core.platform.base import CaptionCheck, PlatformAdapter


class InstagramAdapter(PlatformAdapter):
    key = "instagram"

    def assemble_caption(self, hook: str, body: str, cta: str, hashtags: list[str]) -> str:
        tags = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
        return f"{hook}\n\n{body}\n\n{cta}\n\n{tags}".strip()

    def check_caption(self, caption: str, hashtags: list[str]) -> CaptionCheck:
        base = super().check_caption(caption, hashtags)
        problems = list(base.problems)

        # 첫 125자에서 잘린다. 훅이 그 안에서 끝나야 스크롤을 멈춘다.
        first_line = caption.split("\n", 1)[0]
        if len(first_line) > self.spec.caption_fold_at:
            problems.append(
                f"첫 줄이 {len(first_line)}자다. {self.spec.caption_fold_at}자에서 접히므로 "
                "훅이 잘린다"
            )
        lo, hi = self.spec.hashtag_recommended
        if hashtags and not (lo <= len(hashtags) <= hi):
            problems.append(f"해시태그 권장 범위는 {lo}~{hi}개다 (현재 {len(hashtags)}개)")
        return CaptionCheck(ok=not problems, problems=problems)
