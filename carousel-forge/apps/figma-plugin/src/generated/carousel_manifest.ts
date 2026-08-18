// AUTO-GENERATED — do not edit. Regenerate with `python scripts/codegen.py`.
// source: schemas/carousel_manifest.schema.json

export interface ManifestSlide {
  index: number;
  role: "hook" | "context" | "point" | "proof" | "example" | "summary" | "cta";
  layout_template: string;
  /** 텍스트 없는 배경 원본. null이면 단색/그라디언트. */
  background_url?: string | null;
  /** 배경 이미지가 없을 때의 CSS 배경값 */
  background_fill?: string | null;
  overlay?: {
    type: "scrim" | "gradient" | "none";
    opacity: number;
    color: string;
  } | null;
  copy_blocks: Array<ManifestCopyBlock>;
}

/** 실측 좌표가 붙은 CopyBlock. Figma TextNode 1:1 대응. */
export interface ManifestCopyBlock {
  id: string;
  role: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  align: "left" | "center" | "right" | "justified";
  color: string;
  font: {
    family: string;
    style: string;
    size: number;
    /** em 단위 */
    letter_spacing: number;
    /** 배수 (1.15 = 115%) */
    line_height: number;
  };
  /** 줄 단위 실측 박스. 오버플로 검사·SVG tspan 좌표에 사용. */
  line_boxes?: Array<{
    text: string;
    x: number;
    y: number;
    width: number;
    height: number;
    baseline: number;
  }>;
  /** [start, end) 문자 인덱스 구간. Figma에서 setRangeFills 등으로 강조 처리한다. */
  emphasis_spans?: Array<[number, number]>;
  /** 강조 구간에 적용된 색 */
  emphasis_color?: string | null;
}

/** 백엔드와 Figma 플러그인이 공유하는 계약. 좌표는 Playwright getBoundingClientRect() 실측값만 사용한다. 추정 금지. */
export interface CarouselManifest {
  schema_version: 1;
  set_id: string;
  account: string;
  platform: "instagram" | "xiaohongshu";
  language: "ko" | "zh" | "en";
  canvas: {
    width: number;
    height: number;
    safe_margin_px?: number;
  };
  fonts_required: Array<{
    family: string;
    style: string;
    /** 내보내기 ZIP 안의 상대 경로 (04_reference/fonts/…) */
    file?: string;
  }>;
  slides: Array<ManifestSlide>;
}
