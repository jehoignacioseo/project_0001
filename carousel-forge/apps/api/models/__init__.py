"""SQLModel 테이블 정의.

Alembic이 자동 생성(autogenerate)으로 잡아내려면 모든 테이블이 여기서
import 되어 `SQLModel.metadata`에 등록돼 있어야 한다.
"""

from .account import Account
from .asset import Asset
from .base import new_id, utcnow
from .carousel import CarouselSet, Slide
from .enums import (
    AssetKind,
    FactVerdict,
    GenerationVerdict,
    Language,
    PipelineStage,
    Platform,
    SetStatus,
    SlideRole,
    StyleSourceType,
    TopicInputType,
    VariantType,
)
from .quality import FactCheck, GenerationLog
from .style import StyleDNA
from .topic import TopicBrief

__all__ = [
    "Account",
    "Asset",
    "AssetKind",
    "CarouselSet",
    "FactCheck",
    "FactVerdict",
    "GenerationLog",
    "GenerationVerdict",
    "Language",
    "PipelineStage",
    "Platform",
    "SetStatus",
    "Slide",
    "SlideRole",
    "StyleDNA",
    "StyleSourceType",
    "TopicBrief",
    "TopicInputType",
    "VariantType",
    "new_id",
    "utcnow",
]
