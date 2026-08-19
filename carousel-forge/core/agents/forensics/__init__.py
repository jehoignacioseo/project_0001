"""A1 StyleForensics의 측정 계층.

스타일 추출의 성패는 "무엇을 추출할지의 해상도"에 달려 있다. 그리고 그 절반은
**눈대중이 아니라 실측**이어야 한다 — 색은 픽셀에서, 텍스트 영역은 기하에서,
어미·이모지·해시태그는 캡션 통계에서 나온다.

여기 있는 것은 전부 순수 함수다. 모델은 이 측정값을 해석할 뿐, 측정 자체를
대신하지 않는다.
"""

from .captions import CaptionStats, analyse_captions
from .compare import DnaComparison, FieldMatch, compare_dna, delta_e_2000
from .palette import PaletteReport, Swatch, extract_palette
from .preview import PreviewResult, build_preview_set, render_verification
from .zones import ZoneReport, analyse_text_zones

__all__ = [
    "CaptionStats",
    "DnaComparison",
    "FieldMatch",
    "PaletteReport",
    "PreviewResult",
    "Swatch",
    "ZoneReport",
    "analyse_captions",
    "build_preview_set",
    "analyse_text_zones",
    "compare_dna",
    "delta_e_2000",
    "extract_palette",
    "render_verification",
]
