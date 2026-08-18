// AUTO-GENERATED — do not edit. Regenerate with `python scripts/codegen.py`.
// source: schemas/style_dna.schema.json

export type HexColor = string;

export type Ratio = number;

export type Language = "ko" | "zh" | "en";

export type SlideRole = "hook" | "context" | "point" | "proof" | "example" | "summary" | "cta";

export interface TypeSpec {
  family: string;
  /** 정확 식별이 어려우므로 유사 계열 + 사용 가능한 대체 폰트 쌍으로 저장 */
  fallback?: Array<string>;
  weight: number;
  /** 절대 px가 아니라 캔버스 짧은 변 대비 비율 */
  size_ratio: number;
  letter_spacing_em?: number;
  line_height?: number;
  case?: "as-is" | "upper" | "lower";
}

/** 벤치마크 계정에서 역설계한 스타일 자산. 이 프로그램의 심장. 필드를 임의로 줄이지 않는다. */
export interface StyleDNA {
  identity: {
    archetype: "editorial-minimal" | "meme-chaotic" | "infographic-dense" | "lifestyle-warm" | "luxury-clean" | "zine-collage";
    /** 이 계정을 한 문장으로 */
    one_line: string;
    /** 누가 이걸 저장하는가 */
    target_reader: string;
  };
  visual: {
    palette: {
      primary: Array<HexColor>;
      accent: Array<HexColor>;
      background: Array<HexColor>;
      text: Array<HexColor>;
      usage_ratio: {
        bg: Ratio;
        primary: Ratio;
        accent: Ratio;
      };
    };
    typography: {
      headline: TypeSpec;
      body: TypeSpec;
      accent: TypeSpec;
      korean_font: string;
      chinese_font: string;
      latin_font: string;
      /** 한중영 혼용 시 폰트 폴백 순서 */
      mixed_script_rule: string;
    };
    layout: {
      safe_margin_ratio: Ratio;
      text_zone: "top" | "center" | "bottom" | "split" | "full-bleed";
      text_block_max_lines: number;
      alignment: "left" | "center" | "justified";
      grid: "single" | "two-column" | "card-stack";
      decorations: Array<"underline-highlight" | "number-badge" | "quote-mark" | "divider-rule">;
    };
    imagery: {
      type_mix: {
        photo: Ratio;
        illustration: Ratio;
        solid_or_gradient: Ratio;
      };
      treatment: Array<"film-grain" | "desaturated" | "high-contrast" | "warm-shift" | "duotone">;
      grain_intensity: Ratio;
      /** 인물 등장 여부, 손/제품 등장 방식, 크롭 습관 */
      subject_rules: string;
      overlay: {
        type: "scrim" | "gradient" | "none";
        opacity: Ratio;
      };
    };
  };
  structure: {
    slide_count_range: [number, number];
    slide_count_mode: number;
    hook_type: "question" | "number-promise" | "contrarian" | "pain-point" | "curiosity-gap" | "result-first";
    narrative_pattern: "problem-solution" | "listicle" | "story-arc" | "comparison" | "tutorial" | "myth-bust";
    slide_roles_sequence: Array<SlideRole>;
    cta_type: "save" | "share" | "comment-keyword" | "link-in-bio" | "follow";
    cover_rule: "title-only" | "title+sub" | "title+sub+badge";
  };
  copy: {
    language: Language;
    /** 반말 | 존댓말 | 해요체 | 중국어 구어체 */
    register: string;
    sentence_length_avg: number;
    headline_char_limit: number;
    body_char_limit_per_slide: number;
    emoji_density: Ratio;
    emoji_palette: Array<string>;
    punctuation_habits: string;
    signature_phrases: Array<string>;
    /** 이 계정이 절대 안 쓰는 말 */
    forbidden_words: Array<string>;
  };
  caption: {
    length_range: [number, number];
    /** 첫 줄 훅 공식 (IG는 첫 125자가 접힘 전 노출) */
    first_line_rule: string;
    structure: Array<"hook" | "body" | "line_break" | "cta" | "hashtag_block">;
    hashtag_strategy: {
      count: number;
      mix: {
        broad: number;
        niche: number;
        branded: number;
        community: number;
      };
      placement: "inline" | "end" | "first-comment";
    };
  };
  evidence: {
    /** 최소 6, 권장 12 이상. 6 미만이면 confidence_score < 0.6 */
    sampled_posts: number;
    /** 추출 근거 메모 */
    notes: string;
    /** 샘플 부족으로 추정한 필드 목록 */
    low_confidence_fields: Array<string>;
  };
}
