/**
 * 사양 → 실제 Figma 노드.
 *
 * `code.ts`에서 분리해 둔 이유는 하나다 — **여기가 M6의 완료 기준이 사는 곳**이고,
 * 가짜 `figma` 전역을 끼워 넣으면 Figma 없이도 검증할 수 있기 때문이다.
 * 카피 한 덩어리가 벡터가 아니라 TextNode가 되는지, 폰트를 먼저 불러오는지 같은
 * 것들은 눈으로 확인하기 전에 테스트가 먼저 잡아야 한다.
 */

import type { FontRef, SlideSpec, TextSpec } from "./carousel";

/** 쓸 폰트를 미리 전부 불러온다. 실패한 것은 목록으로 돌려준다. */
export async function loadFonts(fonts: FontRef[]): Promise<FontRef[]> {
  const missing: FontRef[] = [];
  for (const font of fonts) {
    try {
      await figma.loadFontAsync({ family: font.family, style: font.style });
    } catch {
      missing.push(font);
    }
  }
  return missing;
}

export function describeFont(font: FontRef): string {
  return `${font.family} ${font.style}`;
}

export function decodeBackgrounds(
  raw: Record<string, number[]>,
): Map<number, Uint8Array> {
  const out = new Map<number, Uint8Array>();
  for (const [index, bytes] of Object.entries(raw ?? {})) {
    out.set(Number(index), new Uint8Array(bytes));
  }
  return out;
}

export function buildSlide(
  slide: SlideSpec,
  backgrounds: Map<number, Uint8Array>,
): FrameNode {
  const frame = figma.createFrame();
  frame.name = slide.name;
  frame.resize(slide.width, slide.height);
  frame.x = slide.x;
  frame.y = slide.y;
  frame.clipsContent = true;

  const fills: Paint[] = [];
  if (slide.backgroundFill) {
    fills.push({ type: "SOLID", color: slide.backgroundFill });
  }

  const bytes = backgrounds.get(slide.index);
  if (bytes) {
    const image = figma.createImage(bytes);
    fills.push({ type: "IMAGE", scaleMode: "FILL", imageHash: image.hash });
  } else if (!slide.backgroundFill) {
    // 배경이 없으면 흰 프레임이 된다. 빠진 상태가 눈에 띄게 어둡게 둔다.
    fills.push({ type: "SOLID", color: { r: 0.07, g: 0.07, b: 0.07 } });
  }
  frame.fills = fills;

  if (slide.overlay) {
    const overlay = figma.createRectangle();
    overlay.name = "overlay";
    overlay.resize(slide.width, slide.height);
    overlay.x = 0;
    overlay.y = 0;
    overlay.fills = [
      { type: "SOLID", color: slide.overlay.color, opacity: slide.overlay.opacity },
    ];
    overlay.locked = true; // 편집 대상이 아니다 — 실수로 집히지 않게 잠근다
    frame.appendChild(overlay);
  }

  for (const text of slide.texts) {
    frame.appendChild(buildText(text));
  }
  return frame;
}

export function buildText(spec: TextSpec): TextNode {
  const node = figma.createText();
  node.name = spec.id;
  // 폰트를 먼저 지정하고 글자를 넣어야 한다. 순서가 바뀌면 기본 폰트로 들어간다.
  node.fontName = { family: spec.font.family, style: spec.font.style };
  node.characters = spec.characters;

  node.fontSize = spec.fontSize;
  node.letterSpacing = { unit: "PERCENT", value: spec.letterSpacingPercent };
  node.lineHeight = { unit: "PERCENT", value: spec.lineHeightPercent };
  node.fills = [{ type: "SOLID", color: spec.color }];
  node.textAlignHorizontal = spec.align;

  node.x = spec.x;
  node.y = spec.y;
  // 폭만 고정하고 높이는 내용에 맡긴다. 문구를 늘리면 Figma가 알아서 흘린다 —
  // SVG 경로가 못 하는 것이 정확히 이것이다.
  node.textAutoResize = "HEIGHT";
  node.resize(spec.width, node.height);

  for (const span of spec.emphasis) {
    node.setRangeFills(span.start, span.end, [{ type: "SOLID", color: span.color }]);
  }
  return node;
}
