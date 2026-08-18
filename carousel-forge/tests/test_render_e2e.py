"""M1 완료 기준 — 더미 9장이 PNG/SVG/manifest로 끝까지 나오는가.

브라우저를 띄우므로 다른 테스트보다 느리다. `-m "not browser"`로 건너뛸 수 있다.
"""

from __future__ import annotations

import json
import re

import pytest

from core.render import render_and_export
from core.render.manifest import validate_manifest
from tests.fixtures.demo_set import CAPTION, HASHTAGS, demo_render_set, demo_style_dna

pytestmark = pytest.mark.browser


def _normalise(text: str) -> str:
    """줄바꿈에 소비된 공백을 무시하고 글자만 비교한다."""
    return re.sub(r"\s+", "", text)


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    from scripts.make_dummy_backgrounds import gradient_background, write_png

    root = tmp_path_factory.mktemp("export")
    bg_dir = root / "backgrounds"
    for i in range(1, 10):
        write_png(bg_dir / f"bg_{i:02d}.png", 108, 135,
                  gradient_background(108, 135, "#1b1a17", "#0d0c0a", seed=i))

    render_set = demo_render_set()
    report = render_and_export(
        render_set,
        out_root=root / "out",
        background_source_dir=bg_dir,
        style_dna=demo_style_dna(),
        caption=CAPTION,
        hashtags=HASHTAGS,
    )
    manifest = json.loads(report.manifest_path.read_text(encoding="utf-8"))
    return report, manifest, render_set


def test_nine_slides_render_to_upload_images(exported):
    report, _, _ = exported
    assert len(report.upload_paths) == 9
    assert all(p.exists() and p.stat().st_size > 0 for p in report.upload_paths)


def test_export_layout_matches_the_spec(exported):
    report, _, _ = exported
    d = report.export_dir
    for expected in (
        "01_upload/slide_01.jpg", "02_figma/slide_01.svg", "02_figma/manifest.json",
        "02_figma/backgrounds/bg_01.png", "03_copy/overlay_copy.txt", "03_copy/caption.txt",
        "03_copy/hashtags.txt", "03_copy/copy.json", "04_reference/style_dna.json",
        "04_reference/fonts/Pretendard-Bold.woff2", "README.md",
    ):
        assert (d / expected).exists(), expected


def test_manifest_satisfies_the_shared_contract(exported):
    _, manifest, _ = exported
    validate_manifest(manifest)
    assert len(manifest["slides"]) == 9
    assert manifest["canvas"] == {"width": 1080, "height": 1350, "safe_margin_px": 92}


def test_every_copy_block_has_measured_geometry(exported):
    _, manifest, render_set = exported
    declared = sum(len(s.blocks) for s in render_set.slides)
    measured = sum(len(s["copy_blocks"]) for s in manifest["slides"])
    assert measured == declared

    for slide in manifest["slides"]:
        for block in slide["copy_blocks"]:
            assert block["width"] > 0 and block["height"] > 0
            assert block["line_boxes"], block["id"]
            for line in block["line_boxes"]:
                # 실측값이므로 정확히 정수로 떨어질 이유가 없다. 다만 캔버스 안이어야 한다.
                assert 0 <= line["x"] < 1080
                assert 0 <= line["baseline"] <= 1350


def test_text_stays_inside_the_safe_area(exported):
    report, _, _ = exported
    assert report.overflows == [], [str(o) for o in report.overflows]
    assert report.ok


def test_svg_text_is_editable_not_outlined(exported):
    report, manifest, _ = exported
    for slide in manifest["slides"]:
        svg = (report.export_dir / "02_figma" / f"slide_{slide['index']:02d}.svg").read_text(
            encoding="utf-8"
        )
        assert "<path" not in svg          # 아웃라인화되면 Figma에서 수정할 수 없다
        assert "<filter" not in svg and "<mask" not in svg
        for block in slide["copy_blocks"]:
            assert f'<text id="{block["id"]}"' in svg
            # 줄바꿈 지점에서 tspan이 나뉘므로 이어 붙여서 원문과 대조한다.
            text_el = re.search(rf'<text id="{re.escape(block["id"])}".*?</text>', svg, re.DOTALL)
            joined = "".join(re.findall(r"<tspan[^>]*>([^<]*)</tspan>", text_el.group(0)))
            assert _normalise(joined) == _normalise(block["text"])


def test_svg_coordinates_come_from_the_same_measurement_as_the_manifest(exported):
    """PNG·SVG·manifest가 한 번의 실측에서 나왔는지 대조한다 (절대 규칙 #3)."""
    report, manifest, _ = exported
    for slide in manifest["slides"]:
        svg = (report.export_dir / "02_figma" / f"slide_{slide['index']:02d}.svg").read_text(
            encoding="utf-8"
        )
        for block in slide["copy_blocks"]:
            text_el = re.search(rf'<text id="{re.escape(block["id"])}".*?</text>', svg, re.DOTALL)
            assert text_el is not None, block["id"]
            baselines = sorted(
                {round(float(y), 2) for _, y in re.findall(r'<tspan x="([\d.]+)" y="([\d.]+)"', text_el.group(0))}
            )
            assert baselines == sorted({round(line["baseline"], 2) for line in block["line_boxes"]})


def test_background_is_referenced_not_baked(exported):
    """배경과 텍스트는 끝까지 분리 상태다 (절대 규칙 #1)."""
    report, manifest, _ = exported
    for slide in manifest["slides"]:
        assert slide["background_url"].startswith("backgrounds/")
        svg = (report.export_dir / "02_figma" / f"slide_{slide['index']:02d}.svg").read_text(
            encoding="utf-8"
        )
        assert f'href="{slide["background_url"]}"' in svg
        # 배경 원본은 내보내기 안에 그대로 남아 있어야 재편집이 가능하다
        assert (report.export_dir / "02_figma" / slide["background_url"]).exists()


def test_text_transform_is_reflected_in_the_exported_text(exported):
    """화면에 대문자로 보이면 SVG·manifest에도 대문자로 실려야 한다."""
    _, manifest, _ = exported
    eyebrow = next(
        b for s in manifest["slides"] for b in s["copy_blocks"] if b["role"] == "eyebrow"
    )
    assert eyebrow["text"] == eyebrow["text"].upper()


def test_emphasis_survives_into_the_manifest(exported):
    _, manifest, _ = exported
    headline = next(
        b for b in manifest["slides"][0]["copy_blocks"] if b["id"] == "s01_headline"
    )
    assert headline["emphasis_spans"] == [[10, 12]]
    assert headline["emphasis_color"] == "#c8a15a"


def test_copy_files_carry_the_full_text(exported):
    report, _, render_set = exported
    overlay = (report.export_dir / "03_copy" / "overlay_copy.txt").read_text(encoding="utf-8")
    for slide in render_set.slides:
        for block in slide.blocks:
            assert block.text.splitlines()[0] in overlay
    assert CAPTION["hook_line"] in (report.export_dir / "03_copy" / "caption.txt").read_text(
        encoding="utf-8"
    )
