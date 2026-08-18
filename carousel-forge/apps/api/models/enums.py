"""DB에 문자열로 저장되는 열거형. 값은 스펙의 표기를 그대로 따른다."""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    XIAOHONGSHU = "xiaohongshu"


class Language(StrEnum):
    KO = "ko"
    ZH = "zh"
    EN = "en"


class StyleSourceType(StrEnum):
    SCREENSHOTS = "screenshots"
    URL = "url"
    MANUAL = "manual"


class TopicInputType(StrEnum):
    DOCUMENT = "document"
    CHAT = "chat"
    KEYWORD = "keyword"
    PROPOSED = "proposed"


class SetStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    QA = "qa"
    READY = "ready"
    PUBLISHED = "published"
    ARCHIVED = "archived"   # 삭제는 없다. archived만 존재한다.


class VariantType(StrEnum):
    ORIGINAL = "original"
    TRANSLATION = "translation"
    RESTYLE = "restyle"


class SlideRole(StrEnum):
    HOOK = "hook"
    CONTEXT = "context"
    POINT = "point"
    PROOF = "proof"
    EXAMPLE = "example"
    SUMMARY = "summary"
    CTA = "cta"


class AssetKind(StrEnum):
    BACKGROUND = "background"     # 텍스트 없는 배경 원본
    RENDER = "render"             # 배경 + 텍스트 합성본 (파생물)
    EXPORT_SVG = "export_svg"
    EXPORT_ZIP = "export_zip"
    PREVIEW = "preview"           # StyleDNA 검증 렌더


class FactVerdict(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"
    FALSE = "false"


class PipelineStage(StrEnum):
    INTAKE = "intake"
    STYLE_RESOLVE = "style_resolve"
    RESEARCH = "research"
    FACTCHECK = "factcheck"
    ARCHITECT = "architect"
    COPY = "copy"
    VISUAL_GEN = "visual_gen"
    COMPOSE = "compose"
    QUALITY_GATE = "quality_gate"
    LOCALIZE = "localize"
    EXPORT = "export"
    PERSIST = "persist"


class GenerationVerdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    DISCARD = "discard"
    FAIL = "fail"
