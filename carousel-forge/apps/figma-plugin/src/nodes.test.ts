/**
 * M6의 완료 기준 — manifest가 **편집 가능한 텍스트 노드**로 들어가는가.
 *
 * 실제 Figma에서 눈으로 확인하는 일을 대신하지는 못한다. 하지만 "텍스트가
 * 벡터로 들어갔다", "폰트를 안 불러 기본 폰트가 됐다", "카피 한 덩어리가
 * 통째로 빠졌다" 같은 실패는 여기서 먼저 잡힌다.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { buildSpec } from "./carousel.ts";
import type { CarouselManifest } from "./generated/carousel_manifest.ts";
import { installFakeFigma } from "./figma-fake.ts";
import { buildSlide, decodeBackgrounds, loadFonts } from "./nodes.ts";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(here, "..", "..", "..", "tests", "fixtures", "manifest_demo.json");

function loadManifest(): CarouselManifest {
  return JSON.parse(readFileSync(FIXTURE, "utf-8")) as CarouselManifest;
}

async function buildAll(options: { backgrounds?: Record<string, number[]> } = {}) {
  const fake = installFakeFigma();
  const spec = buildSpec(loadManifest());
  const missing = await loadFonts(spec.fonts);
  assert.deepEqual(missing, [], "픽스처의 폰트를 못 불렀다");
  const backgrounds = decodeBackgrounds(options.backgrounds ?? {});
  const frames = spec.slides.map((slide) => buildSlide(slide, backgrounds));
  return { fake, spec, frames };
}

test("카피 블록이 전부 TextNode가 된다 — 벡터가 아니다", async () => {
  const { fake, spec } = await buildAll();
  const expected = spec.slides.reduce((n, s) => n + s.texts.length, 0);

  assert.equal(fake.texts().length, expected);
  // 아웃라인화되면 이 프로그램은 실패한 것이다.
  assert.equal(
    fake.created.filter((n) => n.type === "VECTOR").length,
    0,
    "벡터 노드가 만들어졌다",
  );
});

test("모든 텍스트 노드가 이름을 갖는다 — 레이어에서 찾을 수 있어야 한다", async () => {
  const { fake } = await buildAll();
  for (const text of fake.texts()) {
    assert.ok(text.name.length > 0, "이름 없는 텍스트 노드가 있다");
    assert.match(text.name, /^s\d{2}_/, `레이어 이름 규칙에 안 맞는다: ${text.name}`);
  }
});

test("폰트를 먼저 불러온 뒤에 글자를 넣는다", async () => {
  const { fake } = await buildAll();
  for (const text of fake.texts()) {
    // 가짜 Figma는 loadFontAsync 없이 fontName을 지정하면 던진다. 여기까지 왔다는
    // 것 자체가 순서가 맞았다는 뜻이고, 순서까지 확인한다.
    assert.ok(
      text.order.indexOf("fontName") < text.order.indexOf("characters"),
      `${text.name}: 폰트보다 글자가 먼저 들어갔다`,
    );
  }
});

test("설치되지 않은 폰트는 조용히 대체하지 않고 보고한다", async () => {
  const fake = installFakeFigma();
  const spec = buildSpec(loadManifest());
  fake.markMissing(spec.fonts[0].family, spec.fonts[0].style);

  const missing = await loadFonts(spec.fonts);
  assert.equal(missing.length, 1);
  assert.equal(missing[0].family, spec.fonts[0].family);
});

test("텍스트 내용이 manifest와 글자 그대로 일치한다", async () => {
  const manifest = loadManifest();
  const { fake } = await buildAll();

  const expected = manifest.slides.flatMap((s) => s.copy_blocks.map((b) => b.text));
  const actual = fake.texts().map((t) => t.characters);
  assert.deepEqual(actual, expected);
});

test("높이는 내용에 맡기고 폭만 고정한다 — 문구를 늘리면 다시 흐른다", async () => {
  const { fake } = await buildAll();
  for (const text of fake.texts()) {
    assert.equal(
      text.textAutoResize,
      "HEIGHT",
      `${text.name}: 높이가 고정되면 문구를 늘렸을 때 잘린다`,
    );
  }
});

test("강조 구간이 setRangeFills로 들어간다", async () => {
  const manifest = loadManifest();
  const emphasised = manifest.slides
    .flatMap((s) => s.copy_blocks)
    .filter((b) => (b.emphasis_spans ?? []).length > 0);
  assert.ok(emphasised.length > 0, "픽스처에 강조가 없다");

  const { fake } = await buildAll();
  for (const block of emphasised) {
    const node = fake.texts().find((t) => t.name === block.id);
    if (!node) throw new Error(`${block.id} 노드를 못 찾았다`);
    const spans = block.emphasis_spans ?? [];
    assert.equal(node.rangeFills.length, spans.length);
    assert.deepEqual(
      node.rangeFills.map((r) => [r.start, r.end]),
      spans,
    );
  }
});

test("강조가 없는 블록에는 범위 색을 넣지 않는다", async () => {
  const manifest = loadManifest();
  const plain = manifest.slides
    .flatMap((s) => s.copy_blocks)
    .filter((b) => !(b.emphasis_spans ?? []).length);

  const { fake } = await buildAll();
  for (const block of plain) {
    const node = fake.texts().find((t) => t.name === block.id);
    if (!node) throw new Error(`${block.id} 노드를 못 찾았다`);
    assert.equal(node.rangeFills.length, 0);
  }
});

test("슬라이드마다 프레임 하나가 만들어지고 텍스트가 그 안에 들어간다", async () => {
  const { fake, spec } = await buildAll();
  const frames = fake.frames();
  assert.equal(frames.length, spec.slides.length);

  for (const [i, frame] of frames.entries()) {
    const texts = frame.children.filter((c) => c.type === "TEXT");
    assert.equal(texts.length, spec.slides[i].texts.length);
  }
});

test("프레임 이름에 순번과 역할이 들어간다", async () => {
  const { fake } = await buildAll();
  for (const frame of fake.frames()) {
    assert.match(frame.name, /^Slide \d{2} — \w+$/, `이름 규칙 위반: ${frame.name}`);
  }
});

test("배경 바이트를 주면 이미지 fill이 된다", async () => {
  const png = Array.from(new Uint8Array([0x89, 0x50, 0x4e, 0x47]));
  const { fake } = await buildAll({ backgrounds: { "1": png, "2": png } });

  assert.equal(fake.images.length, 2);
  const withImage = fake
    .frames()
    .filter((f) => (f.fills as { type: string }[]).some((p) => p.type === "IMAGE"));
  assert.equal(withImage.length, 2);
});

test("배경이 없으면 빈 프레임이 아니라 단색으로 둔다", async () => {
  const { fake } = await buildAll();
  for (const frame of fake.frames()) {
    const fills = frame.fills as { type: string }[];
    assert.ok(fills.length > 0, "fill이 비어 흰 프레임이 된다");
  }
});

test("오버레이는 잠긴 채로 들어간다 — 편집 대상이 아니다", async () => {
  const { fake, spec } = await buildAll();
  const withOverlay = spec.slides.filter((s) => s.overlay).length;
  const rectangles = fake.created.filter((n) => n.type === "RECTANGLE");

  assert.equal(rectangles.length, withOverlay);
  for (const rect of rectangles) {
    assert.equal(rect.locked, true, "오버레이가 잠기지 않아 실수로 집힌다");
  }
});

test("좌표와 크기가 manifest 값 그대로 들어간다", async () => {
  const manifest = loadManifest();
  const { fake } = await buildAll();
  const blocks = manifest.slides.flatMap((s) => s.copy_blocks);

  for (const [i, text] of fake.texts().entries()) {
    assert.equal(text.x, blocks[i].x);
    assert.equal(text.y, blocks[i].y);
    assert.equal(text.width, blocks[i].width);
    assert.equal(text.fontSize, blocks[i].font.size);
  }
});
