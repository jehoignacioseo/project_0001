// AUTO-GENERATED — do not edit. Regenerate with `python scripts/codegen.py`.
// source: schemas/outline.schema.json

export interface OutlineSlide {
  index: number;
  role: "hook" | "context" | "point" | "proof" | "example" | "summary" | "cta";
  /** 이 슬라이드가 전달하는 단 하나의 메시지. 카피가 아니라 의도다. */
  single_message: string;
  /** 필요한 비주얼 설명. A7이 배경 프롬프트로 옮긴다. 텍스트 렌더링 요구를 넣지 않는다. */
  visual_brief: string;
  /** 이 슬라이드가 다루는 TopicSchema.supporting_points 항목 */
  supporting_point?: string | null;
  /** 비우면 role에서 정해진다 */
  layout_template?: string | null;
}

/** A4 NarrativeArchitect 산출물. 슬라이드 골격이자 A5 CopySmith와 A7 ArtDirector의 입력이다. */
export interface CarouselOutline {
  title_working: string;
  slide_count: number;
  narrative_pattern: "problem-solution" | "listicle" | "story-arc" | "comparison" | "tutorial" | "myth-bust";
  hook_type: "question" | "number-promise" | "contrarian" | "pain-point" | "curiosity-gap" | "result-first";
  cta_type: "save" | "share" | "comment-keyword" | "link-in-bio" | "follow";
  /** 커버에 전체 리소스의 40%를 쓴다. 훅은 반드시 3개를 만들어 비교한 뒤 고른다. */
  hook_candidates: [{
    text: string;
    /** 왜 이 훅이 스크롤을 멈추는가 */
    rationale: string;
    strength_score: number;
  }, {
    text: string;
    /** 왜 이 훅이 스크롤을 멈추는가 */
    rationale: string;
    strength_score: number;
  }, {
    text: string;
    /** 왜 이 훅이 스크롤을 멈추는가 */
    rationale: string;
    strength_score: number;
  }];
  chosen_hook_index: number;
  slides: Array<OutlineSlide>;
}
