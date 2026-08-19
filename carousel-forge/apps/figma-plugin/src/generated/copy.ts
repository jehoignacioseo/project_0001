// AUTO-GENERATED — do not edit. Regenerate with `python scripts/codegen.py`.
// source: schemas/copy.schema.json

/** 슬라이드 위에 얹히는 편집 가능한 텍스트 한 덩어리. 절대 이미지에 굽지 않는다. */
export interface CopyBlock {
  id: string;
  role: "eyebrow" | "headline" | "subhead" | "body" | "bullet" | "badge" | "caption_note" | "cta" | "page_number";
  text: string;
  max_chars?: number;
  /** [start, end) 문자 인덱스 구간. 강조 처리 대상. */
  emphasis_spans?: Array<[number, number]>;
  editable?: boolean;
}

export interface Caption {
  /** IG는 첫 125자가 접힘 전 노출 — 훅은 그 안에서 끝나야 한다 */
  hook_line: string;
  body: string;
  cta: string;
  /** 해시태그 배치. 비우면 StyleDNA의 hashtag_strategy.placement를 따른다. */
  hashtag_placement?: "inline" | "end" | "first-comment";
}

/** A5 CopySmith 산출물. 슬라이드 오버레이 카피 + 본문 캡션 + 해시태그. */
export interface CopyBundle {
  caption: Caption;
  hashtags: Array<string>;
}
