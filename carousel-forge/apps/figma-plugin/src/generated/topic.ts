// AUTO-GENERATED — do not edit. Regenerate with `python scripts/codegen.py`.
// source: schemas/topic.schema.json

/** A2 TopicIntake가 어떤 입력(문서/채팅/키워드/URL/시스템 제안)이든 수렴시키는 정규화 형태. */
export interface TopicBriefPayload {
  title_working: string;
  /** 이 주제를 어느 각도로 자를 것인가 */
  angle: string;
  audience: string;
  /** 독자가 단 하나만 기억한다면 */
  key_message: string;
  supporting_points: Array<string>;
  /** 검증이 필요한 주장 목록 */
  evidence_needed: Array<string>;
  cta_intent: string;
  constraints: {
    must_include: Array<string>;
    must_avoid: Array<string>;
  };
  /** strict이면 원문에 없는 사실을 창작하지 않는다. 문서 입력의 기본값은 strict. */
  source_fidelity: "strict" | "flexible";
}
