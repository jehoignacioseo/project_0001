/**
 * manifest → Figma 사양 변환 테스트.
 *
 * Figma 안에서만 돌 수 있는 부분은 `code.ts`에 몰아 두고, 값을 옮기는 일은 전부
 * `carousel.ts`에 두었다. 그래서 플러그인 로직의 대부분을 Figma 없이 검증한다.
 *
 * 실제 manifest 픽스처를 쓴다 — 손으로 만든 예시는 스키마가 바뀌어도 통과해서
 * 계약이 갈라진 걸 못 잡는다.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { test } from "node:test";

import {
  boundingBox,
  buildSpec,
  hexToRgb,
  ManifestError,
  requiredFonts,
} from "./carousel.ts";
import type { CarouselManifest } from "./generated/carousel_manifest.ts";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(here, "..", "..", "..", "tests", "fixtures", "manifest_demo.json");

function loadManifest(): CarouselManifest {
  return JSON.parse(readFileSync(FIXTURE, "utf-8")) as CarouselManifest;
}

// ── 색 ──────────────────────────────────────────────────────────────────

test("hex를 Figma의 0~1 RGB로 옮긴다", () => {
  assert.deepEqual(hexToRgb("#000000"), { r: 0, g: 0, b: 0 });
  assert.deepEqual(hexToRgb("#ffffff"), { r: 1, g: 1, b: 1 });
  const gold = hexToRgb("#c8a15a");
  assert.ok(Math.abs(gold.r - 200 / 255) < 1e-9);
});

test("세 자리 축약형도 받는다", () => {
  assert.deepEqual(hexToRgb("#fff"), hexToRgb("#ffffff"));
});

test("색 형식이 틀리면 조용히 검정으로 떨어지지 않는다", () => {
  assert.throws(() => hexToRgb("papayawhip"), ManifestError);
  assert.throws(() => hexToRgb("#12345"), ManifestError);
});

// ── 단위 변환 ───────────────────────────────────────────────────────────

test("자간과 행간을 Figma의 퍼센트로 옮긴다", () => {
  const manifest = loadManifest();
  const block = manifest.slides[0].copy_blocks[0];
  const spec = buildSpec(manifest);
  const text = spec.slides[0].texts[0];

  // manifest는 em/배수, Figma는 퍼센트다. 그대로 넘기면 자간이 100배가 된다.
  assert.equal(text.letterSpacingPercent, block.font.letter_spacing * 100);
  assert.equal(text.lineHeightPercent, block.font.line_height * 100);
});

test("정렬을 Figma 상수로 옮긴다", () => {
  const spec = buildSpec(loadManifest());
  for (const slide of spec.slides) {
    for (const text of slide.texts) {
      assert.ok(["LEFT", "CENTER", "RIGHT", "JUSTIFIED"].includes(text.align));
    }
  }
});

test("모르는 정렬값은 임의로 왼쪽으로 만들지 않는다", () => {
  const manifest = loadManifest();
  (manifest.slides[0].copy_blocks[0] as { align: string }).align = "middle";
  assert.throws(() => buildSpec(manifest), ManifestError);
});

// ── 배치 ────────────────────────────────────────────────────────────────

test("슬라이드를 index 순서로 가로 배치한다", () => {
  const manifest = loadManifest();
  manifest.slides.reverse(); // 순서가 뒤집혀 들어와도
  const spec = buildSpec(manifest);

  assert.deepEqual(
    spec.slides.map((s) => s.index),
    [...spec.slides].map((s) => s.index).sort((a, b) => a - b),
  );
  for (let i = 1; i < spec.slides.length; i += 1) {
    assert.ok(
      spec.slides[i].x > spec.slides[i - 1].x,
      "프레임이 겹치거나 역순으로 놓였다",
    );
  }
});

test("프레임이 서로 겹치지 않는다", () => {
  const spec = buildSpec(loadManifest());
  for (let i = 1; i < spec.slides.length; i += 1) {
    const previous = spec.slides[i - 1];
    assert.ok(spec.slides[i].x >= previous.x + previous.width);
  }
});

test("경계 상자가 모든 프레임을 담는다", () => {
  const spec = buildSpec(loadManifest());
  const box = boundingBox(spec);
  for (const slide of spec.slides) {
    assert.ok(slide.x + slide.width <= box.width);
    assert.ok(slide.height <= box.height);
  }
});

// ── 폰트 ────────────────────────────────────────────────────────────────

test("선언 목록에 없는 폰트도 카피 블록에서 찾아낸다", () => {
  const manifest = loadManifest();
  manifest.fonts_required = []; // 선언이 비어 있어도
  const fonts = requiredFonts(manifest);

  assert.ok(fonts.length > 0, "블록이 쓰는 폰트를 못 찾았다");
  // 못 찾으면 loadFontAsync 없이 characters를 넣게 되고 런타임 에러가 난다.
  const used = new Set(
    manifest.slides.flatMap((s) =>
      s.copy_blocks.map((b) => `${b.font.family} ${b.font.style}`),
    ),
  );
  const found = new Set(fonts.map((f) => `${f.family} ${f.style}`));
  for (const font of used) assert.ok(found.has(font), `${font}가 빠졌다`);
});

test("같은 폰트를 중복해서 싣지 않는다", () => {
  const fonts = requiredFonts(loadManifest());
  const keys = fonts.map((f) => `${f.family} ${f.style}`);
  assert.equal(keys.length, new Set(keys).size);
});

// ── 강조 ────────────────────────────────────────────────────────────────

test("강조 구간이 사양으로 넘어간다", () => {
  const manifest = loadManifest();
  const withEmphasis = manifest.slides
    .flatMap((s) => s.copy_blocks)
    .find((b) => (b.emphasis_spans ?? []).length > 0);
  if (!withEmphasis) throw new Error("픽스처에 강조 구간이 있는 블록이 없다");
  const spans = withEmphasis.emphasis_spans ?? [];

  const spec = buildSpec(manifest);
  const text = spec.slides
    .flatMap((s) => s.texts)
    .find((t) => t.id === withEmphasis.id);
  if (!text) throw new Error(`${withEmphasis.id} 사양을 못 찾았다`);

  assert.equal(text.emphasis.length, spans.length);
  assert.deepEqual(
    text.emphasis.map((e) => [e.start, e.end]),
    spans,
  );
});

test("텍스트를 벗어난 강조 구간은 잘라 맞추지 않고 실패한다", () => {
  const manifest = loadManifest();
  const block = manifest.slides[0].copy_blocks[0];
  block.emphasis_spans = [[0, block.text.length + 5]];
  assert.throws(() => buildSpec(manifest), ManifestError);
});

// ── 계약 ────────────────────────────────────────────────────────────────

test("모르는 manifest 버전은 읽지 않는다", () => {
  const manifest = loadManifest();
  (manifest as { schema_version: number }).schema_version = 2;
  assert.throws(() => buildSpec(manifest), ManifestError);
});

test("슬라이드가 없으면 빈 캔버스를 만들지 않는다", () => {
  const manifest = loadManifest();
  manifest.slides = [];
  assert.throws(() => buildSpec(manifest), ManifestError);
});

test("모든 카피 블록이 텍스트 사양이 된다 — 하나도 흘리지 않는다", () => {
  const manifest = loadManifest();
  const blocks = manifest.slides.reduce((n, s) => n + s.copy_blocks.length, 0);
  const spec = buildSpec(manifest);
  const texts = spec.slides.reduce((n, s) => n + s.texts.length, 0);
  assert.equal(texts, blocks);
});

test("좌표를 그대로 옮긴다 — 플러그인은 좌표를 다시 계산하지 않는다", () => {
  const manifest = loadManifest();
  const spec = buildSpec(manifest);
  for (const [i, slide] of manifest.slides.entries()) {
    for (const [j, block] of slide.copy_blocks.entries()) {
      const text = spec.slides[i].texts[j];
      assert.equal(text.x, block.x);
      assert.equal(text.y, block.y);
      assert.equal(text.width, block.width);
      assert.equal(text.fontSize, block.font.size);
    }
  }
});
