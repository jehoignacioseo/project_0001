"""실측 기하 → manifest.json (Figma 플러그인 계약).

manifest의 좌표는 전부 Playwright `getBoundingClientRect()` 실측값이다.
추정값이 섞이면 PNG와 Figma 결과물이 어긋난다 (절대 규칙 #3).

생성된 manifest는 `schemas/carousel_manifest.schema.json`으로 검증한 뒤에만
파일로 나간다. 계약을 어긴 manifest를 내보내느니 실패하는 편이 낫다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import SCHEMAS_DIR
from core.render.html_renderer import SlideMeasurement
from core.render.model import RenderSet
from core.render.svg_exporter import css_color_to_hex

SCHEMA_PATH = SCHEMAS_DIR / "carousel_manifest.schema.json"


class ManifestError(RuntimeError):
    pass


def _group_runs_into_lines(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 줄에 있는 run을 합쳐 줄 단위 상자를 만든다. 오버플로 검사에 쓴다."""
    lines: list[dict[str, Any]] = []
    for run in runs:
        if lines and abs(lines[-1]["y"] - run["y"]) <= 0.5:
            line = lines[-1]
            right = max(line["x"] + line["width"], run["x"] + run["width"])
            line["x"] = min(line["x"], run["x"])
            line["width"] = right - line["x"]
            line["height"] = max(line["height"], run["height"])
            line["text"] += run["text"]
        else:
            lines.append(
                {
                    "text": run["text"],
                    "x": round(run["x"], 2),
                    "y": round(run["y"], 2),
                    "width": round(run["width"], 2),
                    "height": round(run["height"], 2),
                    "baseline": round(run["baseline"], 2),
                }
            )
    for line in lines:
        line["x"] = round(line["x"], 2)
        line["width"] = round(line["width"], 2)
    return lines


def _block_to_manifest(block: dict[str, Any], source_block: Any) -> dict[str, Any]:
    runs = block["runs"]
    if not runs:
        raise ManifestError(f"{block['id']}: 측정된 텍스트 run이 없다")
    first = runs[0]
    family = first["font_family"].split(",")[0].strip().strip("\"'")
    style = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}.get(
        first["font_weight"], "Regular"
    )
    size = first["font_size"]
    out = {
        "id": block["id"],
        "role": block["role"],
        "text": block["text"],
        "x": round(block["box"]["x"], 2),
        "y": round(block["box"]["y"], 2),
        "width": round(block["box"]["width"], 2),
        "height": round(block["box"]["height"], 2),
        "align": block["align"],
        "color": css_color_to_hex(block["color"]),
        "font": {
            "family": family,
            "style": style,
            "size": round(size, 2),
            # em 단위로 되돌린다. 캔버스가 바뀌어도 그대로 재사용할 수 있다.
            "letter_spacing": round(first["letter_spacing"] / size, 4) if size else 0.0,
            "line_height": round(first["line_height"] / size, 4) if size else 1.0,
        },
        "line_boxes": _group_runs_into_lines(runs),
    }
    if source_block is not None and source_block.emphasis_spans:
        out["emphasis_spans"] = [list(span) for span in source_block.emphasis_spans]
        emphasis_run = next((r for r in runs if r["emphasis"]), None)
        out["emphasis_color"] = css_color_to_hex(emphasis_run["color"]) if emphasis_run else None
    return out


def build_manifest(
    render_set: RenderSet,
    measurements: list[SlideMeasurement],
    *,
    background_href_for: dict[int, str] | None = None,
) -> dict[str, Any]:
    theme = render_set.theme
    canvas = render_set.canvas
    slides: list[dict[str, Any]] = []

    for measurement in measurements:
        source = measurement.source
        source_blocks = {b.id: b for b in (source.blocks if source else [])}
        overlay = None
        if theme.overlay_type != "none":
            overlay = {
                "type": theme.overlay_type,
                "opacity": theme.overlay_opacity,
                "color": css_color_to_hex(theme.palette_background),
            }
        href = (background_href_for or {}).get(measurement.index)
        slides.append(
            {
                "index": measurement.index,
                "role": measurement.role,
                "layout_template": measurement.layout_template,
                "background_url": href,
                "background_fill": (source.background_fill if source else None),
                "overlay": overlay,
                "copy_blocks": [
                    _block_to_manifest(b, source_blocks.get(b["id"])) for b in measurement.blocks
                ],
            }
        )

    return {
        "schema_version": 1,
        "set_id": render_set.set_id,
        "account": render_set.account,
        "platform": render_set.platform,
        "language": render_set.language,
        "canvas": {
            "width": canvas.width,
            "height": canvas.height,
            "safe_margin_px": theme.safe_margin_px,
        },
        "fonts_required": [
            {"family": f["family"], "style": f["style"], "file": f"04_reference/fonts/{f['file']}"}
            for f in render_set.fonts_required()
        ],
        "slides": slides,
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    """JSON Schema 검증. 실패하면 파일로 내보내지 않는다."""
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:  # pragma: no cover - 메시지 가공만
        location = "/".join(str(p) for p in exc.absolute_path)
        raise ManifestError(f"manifest가 계약을 어겼다 ({location}): {exc.message}") from exc


def write_manifest(manifest: dict[str, Any], path: Path) -> Path:
    validate_manifest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
