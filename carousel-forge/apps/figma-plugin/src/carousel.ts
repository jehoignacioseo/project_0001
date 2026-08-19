/**
 * manifest.json → Figma 노드 사양.
 *
 * Figma API를 부르지 않는 순수 변환만 여기에 둔다. 플러그인 로직의 대부분은
 * "manifest의 값을 Figma가 쓰는 단위로 옮기는 일"이고, 그건 Figma 없이도 검증할
 * 수 있어야 한다. `code.ts`는 여기서 나온 사양을 노드로 만들기만 한다.
 *
 * 타입은 `src/generated/`에서 온다 — 백엔드와 같은 JSON Schema에서 생성된 것이라
 * 계약이 갈라질 수 없다.
 */

import type { CarouselManifest, ManifestCopyBlock, ManifestSlide } from "./generated";

export interface RGB {
  r: number;
  g: number;
  b: number;
}

export interface FontRef {
  family: string;
  style: string;
}

export interface TextSpec {
  id: string;
  role: string;
  characters: string;
  x: number;
  y: number;
  width: number;
  font: FontRef;
  fontSize: number;
  /** Figma는 퍼센트를 쓴다. manifest는 em이므로 ×100. */
  letterSpacingPercent: number;
  /** manifest는 배수(1.15), Figma는 퍼센트(115). */
  lineHeightPercent: number;
  color: RGB;
  align: "LEFT" | "CENTER" | "RIGHT" | "JUSTIFIED";
  /** 강조 구간 — Figma에서는 setRangeFills로 넣는다. */
  emphasis: { start: number; end: number; color: RGB }[];
}

export interface SlideSpec {
  index: number;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  backgroundUrl: string | null;
  backgroundFill: RGB | null;
  overlay: { color: RGB; opacity: number } | null;
  texts: TextSpec[];
}

export interface CarouselSpec {
  setId: string;
  account: string;
  platform: string;
  language: string;
  slides: SlideSpec[];
  fonts: FontRef[];
}

/** 프레임 사이 간격. 캔버스 폭에 비례해 두면 규격이 바뀌어도 보기 좋다. */
export const FRAME_GAP_RATIO = 0.093;

export class ManifestError extends Error {}

export function hexToRgb(hex: string): RGB {
  const value = hex.trim().replace(/^#/, "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) {
    throw new ManifestError(`색 값이 #RRGGBB 형식이 아니다: ${hex}`);
  }
  return {
    r: parseInt(full.slice(0, 2), 16) / 255,
    g: parseInt(full.slice(2, 4), 16) / 255,
    b: parseInt(full.slice(4, 6), 16) / 255,
  };
}

const ALIGNMENTS: Record<string, TextSpec["align"]> = {
  left: "LEFT",
  center: "CENTER",
  right: "RIGHT",
  justified: "JUSTIFIED",
};

function toAlign(value: string): TextSpec["align"] {
  const mapped = ALIGNMENTS[value];
  if (!mapped) {
    throw new ManifestError(
      `알 수 없는 정렬: ${value}. 가능한 값: ${Object.keys(ALIGNMENTS).join(", ")}`,
    );
  }
  return mapped;
}

function toTextSpec(block: ManifestCopyBlock): TextSpec {
  if (block.width <= 0) {
    throw new ManifestError(`${block.id}: 폭이 0 이하다 (${block.width})`);
  }
  const emphasisColor = block.emphasis_color
    ? hexToRgb(block.emphasis_color)
    : hexToRgb(block.color);

  const emphasis = (block.emphasis_spans ?? []).map(([start, end]) => {
    if (!(start >= 0 && end > start && end <= block.text.length)) {
      throw new ManifestError(
        `${block.id}: 강조 구간 [${start}, ${end})이 텍스트 길이 ${block.text.length}를 벗어난다`,
      );
    }
    return { start, end, color: emphasisColor };
  });

  return {
    id: block.id,
    role: block.role,
    characters: block.text,
    x: block.x,
    y: block.y,
    width: block.width,
    font: { family: block.font.family, style: block.font.style },
    fontSize: block.font.size,
    letterSpacingPercent: block.font.letter_spacing * 100,
    lineHeightPercent: block.font.line_height * 100,
    color: hexToRgb(block.color),
    align: toAlign(block.align),
    emphasis,
  };
}

function toSlideSpec(
  slide: ManifestSlide,
  manifest: CarouselManifest,
  offsetX: number,
): SlideSpec {
  const { width, height } = manifest.canvas;
  const overlay =
    slide.overlay && slide.overlay.type !== "none" && slide.overlay.opacity > 0
      ? { color: hexToRgb(slide.overlay.color), opacity: slide.overlay.opacity }
      : null;

  return {
    index: slide.index,
    name: `Slide ${String(slide.index).padStart(2, "0")} — ${slide.role}`,
    x: offsetX,
    y: 0,
    width,
    height,
    backgroundUrl: slide.background_url ?? null,
    backgroundFill: slide.background_fill ? hexToRgb(slide.background_fill) : null,
    overlay,
    texts: slide.copy_blocks.map(toTextSpec),
  };
}

/** manifest 전체를 배치까지 끝난 사양으로 바꾼다. */
export function buildSpec(manifest: CarouselManifest): CarouselSpec {
  if (manifest.schema_version !== 1) {
    throw new ManifestError(
      `지원하지 않는 manifest 버전: ${manifest.schema_version}. 이 플러그인은 1을 읽는다.`,
    );
  }
  if (!manifest.slides.length) {
    throw new ManifestError("슬라이드가 없다");
  }

  const gap = Math.round(manifest.canvas.width * FRAME_GAP_RATIO);
  const slides = manifest.slides
    .slice()
    .sort((a, b) => a.index - b.index)
    .map((slide, i) => toSlideSpec(slide, manifest, i * (manifest.canvas.width + gap)));

  return {
    setId: manifest.set_id,
    account: manifest.account,
    platform: manifest.platform,
    language: manifest.language,
    slides,
    fonts: requiredFonts(manifest),
  };
}

/**
 * 실제로 필요한 폰트 목록.
 *
 * manifest의 `fonts_required`를 그대로 믿지 않고 카피 블록에서 다시 모은다.
 * 블록이 쓰는 폰트가 목록에 빠져 있으면 `loadFontAsync` 없이 characters를
 * 설정하게 되고, 그건 런타임 에러다.
 */
export function requiredFonts(manifest: CarouselManifest): FontRef[] {
  const seen = new Map<string, FontRef>();
  for (const declared of manifest.fonts_required ?? []) {
    seen.set(`${declared.family} ${declared.style}`, {
      family: declared.family,
      style: declared.style,
    });
  }
  for (const slide of manifest.slides) {
    for (const block of slide.copy_blocks) {
      const key = `${block.font.family} ${block.font.style}`;
      if (!seen.has(key)) {
        seen.set(key, { family: block.font.family, style: block.font.style });
      }
    }
  }
  return [...seen.values()];
}

/** 캔버스 전체를 담는 크기 — 뷰포트를 맞출 때 쓴다. */
export function boundingBox(spec: CarouselSpec): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  const last = spec.slides[spec.slides.length - 1];
  return {
    x: 0,
    y: 0,
    width: last.x + last.width,
    height: Math.max(...spec.slides.map((s) => s.height)),
  };
}
