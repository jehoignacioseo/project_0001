/**
 * 플러그인 샌드박스 진입점 — UI 메시지를 받아 노드를 만든다.
 *
 * 이 플러그인의 목적은 하나다: **텍스트가 편집 가능한 상태로 들어가는 것.**
 * 각 카피 블록은 독립 TextNode가 되고, 배경은 프레임의 이미지 fill이 된다.
 * 텍스트를 벡터로 만들거나 배경에 굽는 경로는 여기 없다.
 *
 * SVG 드래그앤드롭보다 이 경로를 권하는 이유도 같다. SVG는 줄마다 tspan에
 * 좌표가 박혀 있어 문구를 늘려도 다음 줄로 넘어가지 않지만, TextNode는 폭만
 * 주면 Figma가 알아서 다시 흘린다.
 *
 * 노드를 만드는 일 자체는 `nodes.ts`에 있다 — Figma 없이 검증하기 위해서다.
 */

import { boundingBox, buildSpec, ManifestError } from "./carousel";
import type { CarouselManifest } from "./generated";
import { buildSlide, decodeBackgrounds, describeFont, loadFonts } from "./nodes";

interface BuildMessage {
  type: "build";
  manifest: unknown;
  /** 슬라이드 index → 배경 이미지 바이트. UI가 파일에서 읽어 넘긴다. */
  backgrounds: Record<string, number[]>;
}

interface CancelMessage {
  type: "cancel";
}

type Message = BuildMessage | CancelMessage;

figma.showUI(__html__, { width: 420, height: 560, themeColors: true });

figma.ui.onmessage = async (message: Message) => {
  if (message.type === "cancel") {
    figma.closePlugin();
    return;
  }
  if (message.type !== "build") return;

  try {
    const spec = buildSpec(message.manifest as CarouselManifest);

    const missing = await loadFonts(spec.fonts);
    if (missing.length) {
      // 폰트가 없으면 Figma가 임의로 대체하고 줄바꿈이 달라진다. 조용히 넘어가면
      // "왜 원본과 다르지"의 원인을 찾을 수 없으므로 여기서 멈춘다.
      figma.ui.postMessage({
        type: "error",
        message:
          `폰트가 설치돼 있지 않습니다: ${missing.map(describeFont).join(", ")}\n` +
          "내보내기의 04_reference/fonts/ 폰트를 먼저 설치한 뒤 다시 실행하세요. " +
          "대체 폰트로 만들면 줄바꿈과 크기가 원본과 달라집니다.",
      });
      return;
    }

    const backgrounds = decodeBackgrounds(message.backgrounds);
    const frames = spec.slides.map((slide) => buildSlide(slide, backgrounds));

    const group = figma.group(frames, figma.currentPage);
    group.name = `${spec.account} — ${spec.setId} (${spec.platform}/${spec.language})`;
    figma.currentPage.selection = frames;
    figma.viewport.scrollAndZoomIntoView(frames);

    const box = boundingBox(spec);
    figma.ui.postMessage({
      type: "done",
      slides: spec.slides.length,
      texts: spec.slides.reduce((n, s) => n + s.texts.length, 0),
      missingBackgrounds: spec.slides.filter(
        (s) => s.backgroundUrl && !backgrounds.has(s.index),
      ).length,
      width: box.width,
      height: box.height,
    });
  } catch (error) {
    figma.ui.postMessage({
      type: "error",
      message:
        error instanceof ManifestError
          ? `manifest가 계약을 어겼습니다: ${error.message}`
          : `노드를 만들지 못했습니다: ${String(error)}`,
    });
  }
};
