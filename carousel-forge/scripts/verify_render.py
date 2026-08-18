#!/usr/bin/env python
"""PNG과 SVG가 정말 같은 좌표에서 나왔는지 픽셀로 확인한다.

`demo_render.py`는 manifest와 SVG의 **숫자**가 일치하는지 본다. 이 스크립트는
거기서 한 걸음 더 나가, 내보낸 SVG를 다시 Chromium으로 래스터화해서 업로드용
PNG와 픽셀 단위로 비교한다. 좌표를 어딘가에서 추정했다면 여기서 어긋난다.

    python scripts/verify_render.py storage/exports/deskreset_demo0001_instagram_ko

SVG는 폰트를 시스템에서 찾는다(그래야 Figma에서도 편집된다). 비교 페이지에서는
core/render/fonts의 폰트를 @font-face로 붙여 같은 조건을 만든다.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright  # noqa: E402

from core.config import FONTS_DIR  # noqa: E402
from core.render.html_renderer import chromium_executable  # noqa: E402
from core.render.model import FONT_FILES  # noqa: E402

_STYLE_WEIGHT = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800}

WRAPPER = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
{faces}
* {{ margin:0; padding:0; }}
html, body {{ width:{w}px; height:{h}px; overflow:hidden; background:#000; }}
svg {{ display:block; }}
</style></head><body>{svg}</body></html>
"""

#: 두 이미지를 캔버스에 올려 채널별 차이를 센다.
#:
#: 남는 차이의 대부분은 글자 가장자리 안티에일리어싱과 JPEG 압축이라 0이 될 수
#: 없다. 그래서 "몇 %가 다른가"보다 "1픽셀 밀면 더 잘 맞는가"가 중요한 지표다.
#: 좌표가 밀렸다면 best_shift가 (0,0)이 아니게 나온다.
DIFF_JS = """
async ([aSrc, bSrc, threshold]) => {
  const load = (src) => new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = rej;
    img.src = src;
  });
  const [a, b] = await Promise.all([load(aSrc), load(bSrc)]);
  if (a.width !== b.width || a.height !== b.height) {
    return { error: `크기가 다르다: ${a.width}x${a.height} vs ${b.width}x${b.height}` };
  }
  const draw = (img) => {
    const c = document.createElement("canvas");
    c.width = img.width; c.height = img.height;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.getContext("2d").getImageData(0, 0, img.width, img.height).data;
  };
  const da = draw(a), db = draw(b);
  let differing = 0, total = a.width * a.height, sum = 0, max = 0;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0, p = 0; i < da.length; i += 4, p += 1) {
    const d = Math.max(
      Math.abs(da[i] - db[i]),
      Math.abs(da[i + 1] - db[i + 1]),
      Math.abs(da[i + 2] - db[i + 2]),
    );
    sum += d;
    if (d > max) max = d;
    if (d > threshold) {
      differing += 1;
      const x = p % a.width, y = (p / a.width) | 0;
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
  }
  // 정수 픽셀 이동 탐색: 좌표가 통째로 밀렸는지 본다.
  const shiftScore = (dx, dy) => {
    let s = 0, n = 0;
    for (let y = 2; y < a.height - 2; y += 1) {
      for (let x = 2; x < a.width - 2; x += 1) {
        const i = (y * a.width + x) * 4;
        const j = ((y + dy) * a.width + (x + dx)) * 4;
        s += Math.abs(da[i] - db[j]); n += 1;
      }
    }
    return s / n;
  };
  const shifts = {};
  for (const dy of [-1, 0, 1]) for (const dx of [-1, 0, 1]) shifts[`${dx},${dy}`] = shiftScore(dx, dy);
  let best = "0,0";
  for (const k of Object.keys(shifts)) if (shifts[k] < shifts[best]) best = k;

  return {
    width: a.width, height: a.height, total,
    differing, ratio: differing / total,
    mean_delta: sum / total, max_delta: max,
    bbox: differing ? { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 } : null,
    best_shift: best, shift_scores: shifts,
  };
}
"""


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def font_faces() -> str:
    out = []
    for (family, style), filename in FONT_FILES.items():
        out.append(
            f'@font-face {{ font-family: "{family}"; '
            f'src: url("{(FONTS_DIR / filename).as_uri()}") format("woff2"); '
            f"font-weight: {_STYLE_WEIGHT[style]}; font-style: normal; font-display: block; }}"
        )
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export_dir", type=Path)
    ap.add_argument("--pixel-threshold", type=int, default=24,
                    help="이 값을 넘는 채널 차이를 '다른 픽셀'로 센다 (안티에일리어싱/JPEG 여유)")
    ap.add_argument("--max-diff-ratio", type=float, default=0.025,
                    help="허용 최대 불일치 픽셀 비율 (글자 가장자리 안티에일리어싱 몫)")
    args = ap.parse_args()

    export_dir = args.export_dir.resolve()
    figma_dir = export_dir / "02_figma"
    manifest = json.loads((figma_dir / "manifest.json").read_text(encoding="utf-8"))
    canvas = manifest["canvas"]
    raster_dir = export_dir / ".work" / "svg_raster"
    raster_dir.mkdir(parents=True, exist_ok=True)

    faces = font_faces()
    failures: list[str] = []
    rows: list[tuple[int, dict]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_executable())
        page = browser.new_page(
            viewport={"width": canvas["width"], "height": canvas["height"]},
            device_scale_factor=1,
        )
        try:
            for slide in manifest["slides"]:
                idx = slide["index"]
                svg_path = figma_dir / f"slide_{idx:02d}.svg"
                svg = svg_path.read_text(encoding="utf-8")
                svg = svg.split("?>", 1)[1] if svg.startswith("<?xml") else svg

                # SVG와 같은 폴더에 둬야 backgrounds/ 상대 경로가 그대로 먹는다.
                wrapper = figma_dir / f".verify_{idx:02d}.html"
                wrapper.write_text(
                    WRAPPER.format(faces=faces, w=canvas["width"], h=canvas["height"], svg=svg),
                    encoding="utf-8",
                )
                page.goto(wrapper.as_uri(), wait_until="load")
                page.wait_for_function("document.fonts.status === 'loaded'")
                raster = raster_dir / f"slide_{idx:02d}.png"
                page.screenshot(path=str(raster), type="png")
                wrapper.unlink()

                # 업로드용 이미지는 jpg일 수 있다. 비교 자체는 브라우저가 디코드한다.
                upload = next(
                    (p for p in sorted((export_dir / "01_upload").glob(f"slide_{idx:02d}.*"))),
                    None,
                )
                if upload is None:
                    failures.append(f"슬라이드 {idx}: 업로드용 이미지가 없다")
                    continue

                # file:// 이미지는 캔버스를 오염시켜 getImageData가 막힌다.
                # 브라우저 보안 플래그를 푸는 대신 바이트를 data: URI로 넘긴다.
                result = page.evaluate(
                    DIFF_JS, [data_uri(upload), data_uri(raster), args.pixel_threshold]
                )
                if "error" in result:
                    failures.append(f"슬라이드 {idx}: {result['error']}")
                    continue
                rows.append((idx, result))
                if result["best_shift"] != "0,0":
                    # 이게 진짜 신호다. 좌표를 어디선가 추정했으면 여기서 잡힌다.
                    failures.append(
                        f"슬라이드 {idx}: {result['best_shift']}만큼 밀었을 때 더 잘 맞는다 "
                        "— SVG 좌표가 렌더와 어긋났다"
                    )
                if result["ratio"] > args.max_diff_ratio:
                    failures.append(
                        f"슬라이드 {idx}: 불일치 픽셀 {result['ratio']:.2%} > "
                        f"허용치 {args.max_diff_ratio:.2%} (영역 {result['bbox']})"
                    )
        finally:
            browser.close()

    print(f"PNG ↔ SVG 픽셀 대조 (임계 {args.pixel_threshold}/255, 허용 {args.max_diff_ratio:.2%})")
    print(f"{'슬라이드':>8}  {'불일치':>8}  {'평균차':>7}  {'최적이동':>8}  차이 영역")
    for idx, r in rows:
        bbox = r["bbox"]
        where = "-" if bbox is None else f"x={bbox['x']} y={bbox['y']} {bbox['w']}×{bbox['h']}"
        print(
            f"{idx:>8}  {r['ratio']:>7.3%}  {r['mean_delta']:>7.2f}  "
            f"{r['best_shift']:>8}  {where}"
        )

    if failures:
        print("\n실패:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(
        f"\n{len(rows)}장 모두 최적 이동 (0,0). 남은 차이는 글자 가장자리 안티에일리어싱과 "
        "JPEG 압축 몫이고, SVG는 PNG와 같은 실측 좌표에서 나왔다."
    )
    print(f"SVG 래스터: {raster_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
