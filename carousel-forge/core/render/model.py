"""렌더 입력 모델.

**단일 소스 → 다중 출력**의 그 '단일 소스'가 여기 있다. `RenderSet` 하나에서
PNG(업로드용) / SVG(Figma용) / manifest.json(플러그인용) / TXT(카피용)가 파생된다.

배경과 텍스트는 끝까지 분리 상태로 유지된다 (절대 규칙 #1). `RenderSlide`는
배경 참조와 `blocks`를 따로 들고 있을 뿐, 둘을 합친 결과물을 갖지 않는다.

타이포 크기는 절대 px가 아니라 StyleDNA의 `size_ratio`(캔버스 짧은 변 대비 비율)
에서 계산된다. 플랫폼 규격이 바뀌어도 스타일이 유지되는 이유다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.config import Canvas, PlatformSpec, platform_spec

#: 슬라이드 role → 레이아웃 템플릿. M1은 hook / point / cta 3종을 제공한다.
ROLE_TO_TEMPLATE: dict[str, str] = {
    "hook": "hook",
    "context": "point",
    "point": "point",
    "proof": "point",
    "example": "point",
    "summary": "point",
    "cta": "cta",
}

#: 폰트 파일은 네트워크가 아니라 core/render/fonts에서 로컬로 임베드한다.
#: 웹폰트 네트워크 의존은 렌더 불일치의 원인이다.
FONT_FILES: dict[tuple[str, str], str] = {
    ("Pretendard", "Regular"): "Pretendard-Regular.woff2",
    ("Pretendard", "Bold"): "Pretendard-Bold.woff2",
    ("Pretendard", "ExtraBold"): "Pretendard-ExtraBold.woff2",
    # 중국어(간체). Pretendard에는 한자 글리프가 없어 폴백으로 떨어지고, 그러면
    # 측정한 좌표와 실제 조판이 갈라진다. 굵기는 Pretendard와 같은 이름으로 맞췄다.
    ("Noto Sans SC", "Regular"): "NotoSansSC-Regular.woff2",
    ("Noto Sans SC", "Bold"): "NotoSansSC-Bold.woff2",
    ("Noto Sans SC", "ExtraBold"): "NotoSansSC-ExtraBold.woff2",
}

#: 폰트 패밀리 → 함께 배포해야 하는 라이선스 파일.
#: OFL은 폰트 파일을 재배포할 때 라이선스 사본을 동봉하도록 요구한다. 내보내기
#: 폴더에 폰트만 넣고 라이선스를 빼면 절대 규칙 #10을 절반만 지킨 것이다.
FONT_LICENSES: dict[str, str] = {
    "Pretendard": "Pretendard-LICENSE.txt",
    "Noto Sans SC": "NotoSansSC-LICENSE.txt",
}

#: CSS font-weight → Figma가 이해하는 스타일 이름
WEIGHT_TO_STYLE: dict[int, str] = {400: "Regular", 700: "Bold", 800: "ExtraBold"}


#: CSS에 그대로 들어가는 폰트명이므로 허용 문자를 좁게 잡는다.
_FONT_NAME_RE = re.compile(r"[A-Za-z0-9 \-_]+")


class RenderModelError(ValueError):
    """렌더 입력이 계약을 어겼다. 추정해서 넘어가지 않는다."""


@dataclass(frozen=True)
class TypeStyle:
    """해상도가 적용된 타이포 스펙. size는 실제 px."""

    family: str
    fallback: tuple[str, ...]
    weight: int
    size_px: float
    letter_spacing_em: float
    line_height: float
    case: str = "as-is"

    @property
    def figma_style(self) -> str:
        if self.weight not in WEIGHT_TO_STYLE:
            raise RenderModelError(
                f"weight {self.weight}에 대응하는 폰트 스타일이 없다. "
                f"가능한 값: {sorted(WEIGHT_TO_STYLE)}"
            )
        return WEIGHT_TO_STYLE[self.weight]

    @property
    def css_font_family(self) -> str:
        """CSS font-family 값.

        `<style>` 안으로 그대로 들어가므로 템플릿에서 |safe로 표시된다. 따라서
        폰트명은 여기서 직접 검증한다 — StyleDNA는 외부에서 추출된 데이터이고,
        검증 없이 스타일시트에 흘려보낼 수 없다.
        """
        names = [self.family, *self.fallback]
        for name in names:
            if not _FONT_NAME_RE.fullmatch(name):
                raise RenderModelError(
                    f"폰트 이름에 쓸 수 없는 문자가 있다: {name!r}. "
                    "영문/숫자/공백/하이픈만 허용한다."
                )
        return ", ".join(f'"{n}"' if " " in n else n for n in names)

    @classmethod
    def from_dna(cls, spec: dict[str, Any], short_side: int) -> TypeStyle:
        ratio = float(spec["size_ratio"])
        if not 0 < ratio <= 1:
            raise RenderModelError(f"size_ratio는 0~1 사이 비율이어야 한다: {ratio}")
        return cls(
            family=spec["family"],
            fallback=tuple(spec.get("fallback", [])),
            weight=int(spec["weight"]),
            # 절대 px가 아니라 캔버스 짧은 변 대비 비율에서 계산한다.
            size_px=round(ratio * short_side, 2),
            letter_spacing_em=float(spec.get("letter_spacing_em", 0.0)),
            line_height=float(spec.get("line_height", 1.4)),
            case=spec.get("case", "as-is"),
        )


@dataclass(frozen=True)
class Theme:
    """StyleDNA를 특정 캔버스에 투영한 결과. 렌더가 보는 유일한 스타일 원천."""

    palette_background: str
    palette_text: str
    palette_primary: str
    palette_accent: str
    headline: TypeStyle
    body: TypeStyle
    accent: TypeStyle
    safe_margin_px: int
    text_zone: str
    alignment: str
    text_block_max_lines: int
    decorations: tuple[str, ...]
    overlay_type: str
    overlay_opacity: float
    grain_intensity: float

    @classmethod
    def from_dna(cls, dna: dict[str, Any], spec: PlatformSpec, canvas: Canvas) -> Theme:
        visual = dna["visual"]
        palette = visual["palette"]
        typo = visual["typography"]
        layout = visual["layout"]
        imagery = visual["imagery"]

        # 안전영역: StyleDNA의 비율과 플랫폼 최소값 중 더 넉넉한 쪽을 쓴다.
        # 플랫폼 규격을 밑도는 여백은 허용하지 않는다.
        dna_margin = round(float(layout["safe_margin_ratio"]) * canvas.short_side)
        return cls(
            palette_background=palette["background"][0],
            palette_text=palette["text"][0],
            palette_primary=palette["primary"][0],
            palette_accent=(palette["accent"] or palette["primary"])[0],
            headline=TypeStyle.from_dna(typo["headline"], canvas.short_side),
            body=TypeStyle.from_dna(typo["body"], canvas.short_side),
            accent=TypeStyle.from_dna(typo["accent"], canvas.short_side),
            safe_margin_px=max(dna_margin, spec.safe_margin_px),
            text_zone=layout["text_zone"],
            alignment=layout["alignment"],
            text_block_max_lines=int(layout["text_block_max_lines"]),
            decorations=tuple(layout.get("decorations", [])),
            overlay_type=imagery["overlay"]["type"],
            overlay_opacity=float(imagery["overlay"]["opacity"]),
            grain_intensity=float(imagery.get("grain_intensity", 0.0)),
        )

    def style_for(self, role: str) -> TypeStyle:
        return {
            "eyebrow": self.accent,
            "headline": self.headline,
            "subhead": self.accent,
            "body": self.body,
            "bullet": self.body,
            "badge": self.accent,
            "caption_note": self.accent,
            "cta": self.headline,
            "page_number": self.accent,
        }.get(role, self.body)


@dataclass
class RenderBlock:
    """슬라이드 위의 편집 가능한 텍스트 한 덩어리. 절대 이미지에 굽지 않는다."""

    id: str
    role: str
    text: str
    max_chars: int | None = None
    emphasis_spans: list[tuple[int, int]] = field(default_factory=list)
    color: str | None = None          # None이면 테마 기본 텍스트 색
    emphasis_color: str | None = None
    editable: bool = True

    def __post_init__(self) -> None:
        for start, end in self.emphasis_spans:
            if not 0 <= start < end <= len(self.text):
                raise RenderModelError(
                    f"{self.id}: 강조 구간 [{start}, {end})이 텍스트 길이 {len(self.text)}를 벗어난다"
                )

    def segments(self) -> list[tuple[str, bool]]:
        """(텍스트, 강조여부) 조각으로 쪼갠다. 템플릿이 span을 나눌 때 쓴다."""
        if not self.emphasis_spans:
            return [(self.text, False)]
        spans = sorted(self.emphasis_spans)
        out: list[tuple[str, bool]] = []
        cursor = 0
        for start, end in spans:
            if start < cursor:
                raise RenderModelError(f"{self.id}: 강조 구간이 겹친다")
            if start > cursor:
                out.append((self.text[cursor:start], False))
            out.append((self.text[start:end], True))
            cursor = end
        if cursor < len(self.text):
            out.append((self.text[cursor:], False))
        return out


@dataclass
class RenderSlide:
    index: int
    role: str
    blocks: list[RenderBlock]
    #: 텍스트가 없는 배경 원본. 내보내기 루트 기준 상대 경로.
    background: str | None = None
    #: 배경 이미지가 없을 때의 CSS 배경값 (단색·그라디언트)
    background_fill: str | None = None
    layout_template: str | None = None
    notes: str | None = None

    #: A8 오토핏이 조절하는 값들. 스타일 자체를 바꾸는 게 아니라 **이 슬라이드만**
    #: 조금 줄여 안전영역에 넣는 것이므로 StyleDNA가 아니라 슬라이드에 붙는다.
    fit_scale: float = 1.0        # 폰트 크기 배수
    tracking_scale: float = 1.0   # 자간 배수
    overlay_boost: float = 0.0    # 대비 확보용 스크림 추가 불투명도

    def template(self) -> str:
        if self.layout_template:
            return self.layout_template
        if self.role not in ROLE_TO_TEMPLATE:
            raise RenderModelError(f"템플릿이 매핑되지 않은 role: {self.role}")
        return ROLE_TO_TEMPLATE[self.role]


@dataclass
class RenderSet:
    set_id: str
    account: str
    platform: str
    language: str
    theme: Theme
    slides: list[RenderSlide]
    canvas_variant: str | None = None

    @property
    def spec(self) -> PlatformSpec:
        return platform_spec(self.platform)

    @property
    def canvas(self) -> Canvas:
        return self.spec.canvas_for(self.canvas_variant)

    def validate(self) -> None:
        """렌더 전 계약 검사. 통과하지 못하면 렌더하지 않는다."""
        problems: list[str] = []
        count = len(self.slides)
        if not self.spec.min_slides <= count <= self.spec.max_slides:
            problems.append(
                f"{self.platform}의 슬라이드 허용 범위는 "
                f"{self.spec.min_slides}~{self.spec.max_slides}장인데 {count}장이다"
            )
        expected = list(range(1, count + 1))
        if [s.index for s in self.slides] != expected:
            problems.append(f"슬라이드 index가 1..{count} 연속이 아니다")
        for slide in self.slides:
            slide.template()  # 매핑 없는 role이면 여기서 예외
            for block in slide.blocks:
                if block.max_chars is not None and len(block.text) > block.max_chars:
                    problems.append(
                        f"슬라이드 {slide.index} {block.id}: {len(block.text)}자가 "
                        f"상한 {block.max_chars}자를 넘는다"
                    )
        if problems:
            raise RenderModelError("렌더 입력이 계약을 어겼다:\n  - " + "\n  - ".join(problems))

    def fonts_required(self) -> list[dict[str, str]]:
        seen: dict[tuple[str, str], dict[str, str]] = {}
        for style in (self.theme.headline, self.theme.body, self.theme.accent):
            key = (style.family, style.figma_style)
            if key in seen:
                continue
            file = FONT_FILES.get(key)
            if file is None:
                raise RenderModelError(
                    f"임베드할 폰트 파일이 없다: {key}. core/render/fonts에 넣고 "
                    "FONT_FILES에 등록하라 (상업적 사용 가능 폰트만)."
                )
            seen[key] = {"family": style.family, "style": style.figma_style, "file": file}
        return list(seen.values())
