"""미리 만들어 둔 배경을 그대로 쓰는 프로바이더.

파이프라인은 배경이 어디서 왔는지 몰라야 한다. 이 프로바이더는 바깥에서
(다른 도구로, 혹은 사람이) 만든 이미지를 슬롯에 끼워 넣는 통로다.

쓰임새 둘:
  - 이미지 모델을 in-process로 부를 수 없는 환경에서 실제 생성물을 넣어 볼 때
  - 사용자가 직접 고른 배경을 쓰고 싶을 때
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.providers.image.base import ImageProvider, ImageRequest, ImageResult


class NoMoreImages(RuntimeError):
    """준비된 이미지가 떨어졌다. 조용히 재사용하지 않는다 — 같은 배경이 두 번
    쓰이면 캐러셀이 아니라 반복이 된다."""


@dataclass
class FileProvider(ImageProvider):
    """정해진 파일 목록을 순서대로 내준다."""

    paths: list[Path] = field(default_factory=list)
    key: str = "files"
    _cursor: int = 0

    @classmethod
    def from_dir(cls, directory: Path, pattern: str = "*.png") -> FileProvider:
        found = sorted(directory.glob(pattern))
        if not found:
            raise FileNotFoundError(f"{directory}에 {pattern} 파일이 없다")
        return cls(paths=found)

    def generate(self, request: ImageRequest) -> ImageResult:
        self.assert_no_text_request(request.prompt)
        if self._cursor >= len(self.paths):
            raise NoMoreImages(
                f"준비된 배경이 {len(self.paths)}장인데 {self._cursor + 1}번째 요청이 왔다. "
                "재생성 루프가 돌면 요청이 슬라이드 수보다 많아진다 — 여유분을 더 넣어라."
            )
        path = self.paths[self._cursor]
        self._cursor += 1

        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size

        return ImageResult(
            path=str(path),
            width=width,
            height=height,
            provider=self.key,
            seed=request.seed,
            prompt=request.prompt,
        )
