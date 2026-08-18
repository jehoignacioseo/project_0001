"""GPT-Image 폴백 프로바이더. M4."""

from __future__ import annotations

from core.providers.image.base import ImageProvider, ImageRequest, ImageResult


class GptImageProvider(ImageProvider):
    key = "gpt_image"

    def generate(self, request: ImageRequest) -> ImageResult:
        self.assert_no_text_request(request.prompt)
        raise NotImplementedError("GPT-Image 폴백은 M4에서 붙는다.")
