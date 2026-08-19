"""설정 로더 — 코드가 규격을 아는 유일한 통로.

절대 규칙 #2: 플랫폼 규격을 코드에 하드코딩하지 않는다.
`config/*.yaml`을 읽는 곳은 여기뿐이고, 나머지 코드는 이 모듈을 통해서만 접근한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = Path(os.environ.get("CAROUSEL_FORGE_CONFIG_DIR", ROOT / "config"))
STORAGE_DIR = Path(os.environ.get("CAROUSEL_FORGE_STORAGE_DIR", ROOT / "storage"))
FONTS_DIR = ROOT / "core" / "render" / "fonts"
TEMPLATES_DIR = ROOT / "core" / "render" / "templates"
SCHEMAS_DIR = ROOT / "schemas"

STALE_AFTER = timedelta(days=180)


class ConfigError(RuntimeError):
    """설정 파일이 없거나 규격에 맞지 않을 때. 조용히 기본값으로 넘어가지 않는다."""


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise ConfigError(f"설정 파일이 없다: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"설정 파일이 매핑이 아니다: {path}")
    return data


@dataclass(frozen=True)
class Canvas:
    width: int
    height: int
    ratio: str

    @property
    def short_side(self) -> int:
        """StyleDNA의 size_ratio는 '캔버스 짧은 변 대비 비율'로 정의된다."""
        return min(self.width, self.height)


@dataclass(frozen=True)
class PlatformSpec:
    """`config/platforms.yaml`의 한 플랫폼 블록. 코드는 이 객체만 본다."""

    key: str
    display_name: str
    canvas: Canvas
    alt_canvas: dict[str, Canvas]
    max_slides: int
    min_slides: int
    caption_max_chars: int
    caption_fold_at: int
    hashtag_max: int
    hashtag_recommended: tuple[int, int]
    safe_margin_px: int
    export_format: tuple[str, ...]
    quality: int
    title_max_chars: int | None
    body_max_chars: int | None
    cover_info_density: str
    #: 커버에 실릴 것으로 기대되는 최소 블록 수. 플랫폼 규격이 아니라
    #: "커버 정보 밀도" 문화를 판정 가능한 수치로 옮긴 값이라 경고에만 쓴다.
    cover_min_blocks: int
    #: 해시태그 표기 틀. `{tag}` 자리에 '#' 없는 태그 이름이 들어간다.
    topic_tag_format: str
    emoji_density: str
    default_language: str
    culture_prompt: str

    def canvas_for(self, variant: str | None = None) -> Canvas:
        if variant in (None, "default"):
            return self.canvas
        if variant not in self.alt_canvas:
            raise ConfigError(
                f"{self.key}에 '{variant}' 캔버스가 없다. "
                f"가능한 값: default, {', '.join(self.alt_canvas)}"
            )
        return self.alt_canvas[variant]


def _canvas(raw: dict[str, Any]) -> Canvas:
    return Canvas(width=int(raw["width"]), height=int(raw["height"]), ratio=str(raw["ratio"]))


@lru_cache(maxsize=None)
def platform_spec(key: str) -> PlatformSpec:
    raw = load_yaml("platforms.yaml")
    defaults = raw.get("defaults", {})
    if key not in raw or key.startswith("_") or key == "defaults":
        available = [k for k in raw if not k.startswith("_") and k != "defaults"]
        raise ConfigError(f"알 수 없는 플랫폼: {key!r}. 가능한 값: {available}")
    block = {**defaults, **raw[key]}
    lo, hi = block.get("hashtag_recommended", [0, block["hashtag_max"]])
    return PlatformSpec(
        key=key,
        display_name=block.get("display_name", key),
        canvas=_canvas(block["canvas"]),
        alt_canvas={k: _canvas(v) for k, v in (block.get("alt_canvas") or {}).items()},
        max_slides=int(block["max_slides"]),
        min_slides=int(block.get("min_slides", 1)),
        caption_max_chars=int(block["caption_max_chars"]),
        caption_fold_at=int(block["caption_fold_at"]),
        hashtag_max=int(block["hashtag_max"]),
        hashtag_recommended=(int(lo), int(hi)),
        safe_margin_px=int(block["safe_margin_px"]),
        export_format=tuple(block["export_format"]),
        quality=int(block["quality"]),
        title_max_chars=block.get("title_max_chars"),
        body_max_chars=block.get("body_max_chars"),
        cover_info_density=block.get("cover_info_density", "low"),
        cover_min_blocks=int(block.get("cover_min_blocks", 1)),
        topic_tag_format=str(block.get("topic_tag_format", "#{tag}")),
        emoji_density=block.get("emoji_density", "low"),
        default_language=block.get("default_language", "ko"),
        culture_prompt=(block.get("culture_prompt") or "").strip(),
    )


def platform_keys() -> list[str]:
    raw = load_yaml("platforms.yaml")
    return [k for k in raw if not k.startswith("_") and k != "defaults"]


def platforms_verified_at() -> date | None:
    meta = load_yaml("platforms.yaml").get("_meta", {})
    value = meta.get("verified_at")
    return date.fromisoformat(str(value)) if value else None


def platforms_are_stale(today: date | None = None) -> bool:
    """규격은 변한다. 마지막 확인일이 오래되면 파이프라인이 경고하도록 한다."""
    verified = platforms_verified_at()
    if verified is None:
        return True
    return (today or date.today()) - verified > STALE_AFTER


@dataclass(frozen=True)
class LanguageSpec:
    """`config/localization.yaml`의 languages 한 항목."""

    code: str
    display_name: str
    script: str
    monospaced_script: bool
    register_note: str


@dataclass(frozen=True)
class LocalizationPair:
    """출발 언어 → 도착 언어 한 쌍."""

    source: str
    target: str
    #: 같은 의미를 쓸 때 도착 언어가 필요로 하는 글자수 비율 (최소, 최대)
    char_ratio: tuple[float, float]
    guidance: str
    hashtag_note: str

    @property
    def hard_ratio(self) -> float:
        """하드 제약으로 쓸 비율. 상한이다 — 짧게 쓴 것은 위반이 아니다."""
        return self.char_ratio[1]


@lru_cache(maxsize=None)
def language_spec(code: str) -> LanguageSpec:
    languages = load_yaml("localization.yaml").get("languages", {})
    if code not in languages:
        raise ConfigError(
            f"알 수 없는 언어: {code!r}. config/localization.yaml에 정의된 값: "
            f"{sorted(languages)}"
        )
    block = languages[code]
    return LanguageSpec(
        code=code,
        display_name=block.get("display_name", code),
        script=block.get("script", ""),
        monospaced_script=bool(block.get("monospaced_script", False)),
        register_note=(block.get("register_note") or "").strip(),
    )


def language_keys() -> list[str]:
    return sorted(load_yaml("localization.yaml").get("languages", {}))


@lru_cache(maxsize=None)
def localization_pair(source: str, target: str) -> LocalizationPair:
    """언어 쌍 설정. 없는 쌍을 임의의 기본값으로 대신하지 않는다."""
    pairs = load_yaml("localization.yaml").get("pairs", {})
    key = f"{source}->{target}"
    if key not in pairs:
        raise ConfigError(
            f"현지화 설정이 없는 언어 쌍: {key}. config/localization.yaml에 "
            f"추가하라. 정의된 쌍: {sorted(pairs)}"
        )
    block = pairs[key]
    ratio = block["char_ratio"]
    if len(ratio) != 2 or not 0 < ratio[0] <= ratio[1] <= 2:
        raise ConfigError(f"{key}.char_ratio가 [최소, 최대] 형태가 아니다: {ratio}")
    return LocalizationPair(
        source=source,
        target=target,
        char_ratio=(float(ratio[0]), float(ratio[1])),
        guidance=(block.get("guidance") or "").strip(),
        hashtag_note=(block.get("hashtag_note") or "").strip(),
    )


def quality_rules() -> dict[str, Any]:
    return load_yaml("quality_rules.yaml")


def model_routing() -> dict[str, Any]:
    return load_yaml("models.yaml")


def database_url() -> str:
    """개발은 SQLite, 운영은 PostgreSQL. SQLModel이 차이를 흡수한다."""
    return os.environ.get(
        "CAROUSEL_FORGE_DATABASE_URL",
        f"sqlite:///{(STORAGE_DIR / 'carousel_forge.db').as_posix()}",
    )
