"""단일 소스 → 다중 출력.

`RenderSet` 하나에서 PNG(업로드용) / SVG(Figma용) / manifest.json(플러그인용) /
TXT(카피용)가 파생된다. 출력물 간 불일치가 원천 차단되는 이유는 넷이 모두 같은
한 번의 렌더에서 나오기 때문이다.

내보내기 구조 (섹션 6.1):

    {account}_{set_id}_{platform}_{lang}/
    ├── 01_upload/      slide_01.jpg …          그대로 업로드
    ├── 02_figma/       slide_01.svg, backgrounds/, manifest.json
    ├── 03_copy/        overlay_copy.txt, caption.txt, hashtags.txt, copy.json
    ├── 04_reference/   style_dna.json, fonts/
    └── README.md
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import FONTS_DIR
from core.render.geometry import Overflow, find_overflows
from core.render.html_renderer import RenderError, SlideMeasurement, SlideRenderer
from core.render.manifest import build_manifest, write_manifest
from core.render.model import FONT_FILES, FONT_LICENSES, RenderSet
from core.render.svg_exporter import build_svg

README = """# {account} — {set_id}

이 폴더는 Carousel Forge가 만든 캐러셀 1세트다.

## 폴더 구성

- `01_upload/` — 합성이 끝난 업로드용 이미지. 그대로 올리면 된다.
- `02_figma/` — 편집용. 텍스트는 이미지에 구워져 있지 않다.
- `03_copy/` — 오버레이 카피와 본문 캡션, 해시태그 (복붙용).
- `04_reference/` — 스타일 DNA와 사용 폰트.

## Figma로 가져오는 방법

### 방법 1 — 플러그인 (권장)
1. Carousel Forge 플러그인을 실행한다.
2. `02_figma/manifest.json`을 지정한다.
3. 슬라이드마다 프레임이 만들어지고, 카피는 각각 독립 TextNode로 들어온다.

### 방법 2 — SVG 드래그앤드롭
1. **먼저 `04_reference/fonts/`의 폰트를 시스템에 설치한다.**
   폰트가 없으면 Figma가 임의의 폰트로 대체하면서 줄바꿈이 달라진다.
2. `02_figma/slide_01.svg` … 파일을 Figma 캔버스로 끌어다 놓는다.
3. 텍스트를 더블클릭해 곧바로 수정할 수 있는지 확인한다. 만약 클릭했을 때
   벡터 도형(Vector)으로 잡힌다면 그 SVG는 잘못 만들어진 것이다 — 보고해 달라.

## 필요한 폰트

{fonts}
"""


@dataclass
class RenderReport:
    """렌더 결과와 그 품질 사실 관계. 통과 판정은 A9 QualityGate가 따로 내린다."""

    set_id: str
    export_dir: Path
    slides: list[SlideMeasurement]
    manifest_path: Path
    svg_paths: list[Path]
    upload_paths: list[Path]
    overflows: list[Overflow] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.overflows

    def summary(self) -> str:
        lines = [
            f"세트 {self.set_id}: 슬라이드 {len(self.slides)}장",
            f"  업로드용 이미지 {len(self.upload_paths)}개, SVG {len(self.svg_paths)}개",
            f"  manifest: {self.manifest_path}",
        ]
        if self.overflows:
            lines.append(f"  안전영역 침범 {len(self.overflows)}건:")
            lines += [f"    - {o}" for o in self.overflows]
        else:
            lines.append("  안전영역 침범 없음")
        return "\n".join(lines)


def export_dir_name(render_set: RenderSet) -> str:
    return f"{render_set.account}_{render_set.set_id}_{render_set.platform}_{render_set.language}"


def render_and_export(
    render_set: RenderSet,
    *,
    out_root: Path,
    background_source_dir: Path | None = None,
    style_dna: dict[str, Any] | None = None,
    caption: dict[str, str] | None = None,
    hashtags: list[str] | None = None,
    embed_background_in_svg: bool = False,
) -> RenderReport:
    export_dir = out_root / export_dir_name(render_set)
    upload_dir = export_dir / "01_upload"
    figma_dir = export_dir / "02_figma"
    bg_dir = figma_dir / "backgrounds"
    copy_dir = export_dir / "03_copy"
    ref_dir = export_dir / "04_reference"
    work_dir = export_dir / ".work"

    for d in (upload_dir, figma_dir, bg_dir, copy_dir, ref_dir / "fonts", work_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 배경 원본을 내보내기 폴더로 먼저 복사한다. HTML·SVG·manifest가 모두
    # 같은 상대 경로(backgrounds/bg_XX.png)를 가리키게 하기 위해서다.
    for slide in render_set.slides:
        if not slide.background:
            continue
        if background_source_dir is None:
            raise ValueError("배경이 있는 슬라이드가 있는데 background_source_dir이 없다")
        src = background_source_dir / slide.background
        if not src.exists():
            raise FileNotFoundError(f"배경 파일이 없다: {src}")
        shutil.copyfile(src, bg_dir / Path(slide.background).name)

    spec = render_set.spec
    image_format = spec.export_format[0]

    renderer = SlideRenderer()
    measurements = renderer.render_set(
        render_set,
        work_dir=work_dir,
        png_dir=upload_dir,
        background_dir=bg_dir,
        image_format=image_format,
        quality=spec.quality,
    )

    background_href = {
        m.index: f"backgrounds/{Path(m.source.background).name}"
        for m in measurements
        if m.source and m.source.background
    }

    svg_paths: list[Path] = []
    for measurement in measurements:
        href = background_href.get(measurement.index)
        svg = build_svg(
            render_set,
            measurement,
            background_href=href,
            embed_background=embed_background_in_svg,
            background_file=(bg_dir / Path(href).name) if href else None,
        )
        svg_path = figma_dir / f"slide_{measurement.index:02d}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        svg_paths.append(svg_path)

    manifest = build_manifest(render_set, measurements, background_href_for=background_href)
    manifest_path = write_manifest(manifest, figma_dir / "manifest.json")

    _write_copy_files(render_set, copy_dir, caption=caption, hashtags=hashtags)
    _write_reference(render_set, ref_dir, style_dna=style_dna)
    (export_dir / "README.md").write_text(
        README.format(
            account=render_set.account,
            set_id=render_set.set_id,
            fonts="\n".join(
                f"- {f['family']} {f['style']} (`04_reference/fonts/{f['file']}`)"
                for f in render_set.fonts_required()
            ),
        ),
        encoding="utf-8",
    )

    overflows = [o for m in measurements for o in find_overflows(m)]
    return RenderReport(
        set_id=render_set.set_id,
        export_dir=export_dir,
        slides=measurements,
        manifest_path=manifest_path,
        svg_paths=svg_paths,
        upload_paths=[m.png_path for m in measurements if m.png_path],
        overflows=overflows,
    )


def _write_copy_files(
    render_set: RenderSet,
    copy_dir: Path,
    *,
    caption: dict[str, str] | None,
    hashtags: list[str] | None,
) -> None:
    lines: list[str] = []
    structured: list[dict[str, Any]] = []
    for slide in render_set.slides:
        lines.append(f"── {slide.index:02d} · {slide.role} ──")
        blocks = []
        for block in slide.blocks:
            lines.append(f"[{block.role}] {block.text}")
            blocks.append({"id": block.id, "role": block.role, "text": block.text})
        lines.append("")
        structured.append({"index": slide.index, "role": slide.role, "copy_blocks": blocks})

    (copy_dir / "overlay_copy.txt").write_text("\n".join(lines), encoding="utf-8")

    caption = caption or {}
    caption_text = "\n\n".join(
        part for part in (caption.get("hook_line"), caption.get("body"), caption.get("cta")) if part
    )
    (copy_dir / "caption.txt").write_text(caption_text + "\n", encoding="utf-8")
    (copy_dir / "hashtags.txt").write_text(" ".join(hashtags or []) + "\n", encoding="utf-8")
    (copy_dir / "copy.json").write_text(
        json.dumps(
            {"slides": structured, "caption": caption, "hashtags": hashtags or []},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_reference(render_set: RenderSet, ref_dir: Path, *, style_dna: dict[str, Any] | None) -> None:
    if style_dna is not None:
        (ref_dir / "style_dna.json").write_text(
            json.dumps(style_dna, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    required = render_set.fonts_required()
    for font in required:
        src = FONTS_DIR / font["file"]
        shutil.copyfile(src, ref_dir / "fonts" / font["file"])
    # 폰트를 넣었으면 라이선스도 같이 넣는다 (절대 규칙 #10).
    for family in {f["family"] for f in required}:
        name = FONT_LICENSES.get(family)
        if name is None:
            raise RenderError(
                f"{family}의 라이선스 파일이 등록돼 있지 않다. "
                "core.render.model.FONT_LICENSES에 추가하라 — 폰트를 라이선스 없이 "
                "내보내지 않는다."
            )
        license_file = FONTS_DIR / name
        if not license_file.exists():
            raise RenderError(f"라이선스 파일이 없다: {license_file}")
        shutil.copyfile(license_file, ref_dir / "fonts" / name)
