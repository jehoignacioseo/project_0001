"""Higgsfield 프로바이더 (1순위). Soul/Element로 인물·오브젝트 정체성을 고정한다. M4."""

from __future__ import annotations

from core.providers.image.base import ImageProvider, ImageRequest, ImageResult


class HiggsfieldProvider(ImageProvider):
    key = "higgsfield"

    def generate(self, request: ImageRequest) -> ImageResult:
        self.assert_no_text_request(request.prompt)
        raise NotImplementedError("Higgsfield 배경 생성은 M4에서 붙는다.")
