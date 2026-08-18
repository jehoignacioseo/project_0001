# CAROUSEL FORGE — 빌드 지시문 (v1.0)

> **이 문서의 용도**: Claude Code(또는 동급 코딩 에이전트)에 그대로 투입하는 구현 지시문.
> 에이전트는 이 문서를 단일 진실 소스(Single Source of Truth)로 삼아 코드베이스를 구축한다.
> 사양이 모호한 지점은 임의 추정하지 말고 `OPEN_QUESTIONS.md`에 기록한 뒤 기본값으로 진행한다.

---

## 0. 한 줄 정의

**스타일(벤치마크 계정 DNA) × 주제(임의 입력) → 인스타그램/샤오홍슈에 즉시 업로드 가능한 캐러셀 완성본(이미지 + 오버레이 카피 + 본문) → Figma 편집 가능 형태로 내보내기 → 계정별 DB 축적.**

핵심 설계 철학 3가지:

1. **텍스트는 절대 이미지에 굽지 않는다(Never bake text).** 배경 이미지와 텍스트 레이어는 끝까지 분리 상태로 유지되며, 최종 합성은 렌더 단계에서만 일어난다. 이것이 Figma 편집 가능성의 전제다.
2. **단일 소스 → 다중 출력(Single Source, Multi Target).** 하나의 `CarouselSet` 데이터 객체에서 PNG(업로드용) / SVG(Figma용) / JSON(플러그인용) / TXT(카피용)가 파생된다. 출력물 간 불일치가 원천 차단된다.
3. **품질 게이트는 통과 여부가 아니라 폐기 권한을 가진다.** 파이프라인이 "완료"된 것은 성공이 아니다. 기준 미달이면 자동 폐기 후 재생성하며, 재생성 한계 도달 시 실패로 보고한다. 애매한 결과물을 통과시키지 않는다.

---

## 1. 기술 스택 (확정)

| 레이어 | 선택 | 이유 |
|---|---|---|
| 코어 백엔드 | **Python 3.11+ / FastAPI** | 파이프라인·에이전트 오케스트레이션·데이터 처리에 유리 |
| DB | **SQLite (개발) → PostgreSQL (운영)** | SQLModel로 추상화해 마이그레이션 비용 0 |
| ORM | **SQLModel + Alembic** | 타입 안전 + 마이그레이션 |
| 렌더 엔진 | **Playwright(Chromium) + HTML/CSS 템플릿** | 웹폰트·한글/중문 조판 정밀 제어. Pillow 직접 드로잉 금지 |
| 벡터 출력 | **동일 HTML 템플릿 → SVG 직렬화** | PNG와 SVG가 같은 소스에서 나오므로 좌표 오차 없음 |
| 이미지 생성 | **Higgsfield MCP (1순위)** / GPT-Image / Nano Banana (폴백) | 기존 파이프라인 자산 재사용 |
| 리서치·팩트체크 | **web_search + web_fetch (병렬)** | |
| 프론트엔드 | **Next.js 14 (App Router) + Tailwind + shadcn/ui** | |
| Figma 연동 | **자체 Figma 플러그인 (TypeScript)** | Figma REST API는 파일 생성 불가 → 플러그인 필수 |
| 작업 큐 | **Celery + Redis** (또는 초기엔 FastAPI BackgroundTasks) | 생성 작업은 수 분 단위 |
| 스키마 공유 | **JSON Schema → Pydantic + TS 타입 자동 생성** | 백엔드/플러그인 계약 동기화 |

> **금지 사항**: 이미지 위에 텍스트를 굽는 Pillow 기반 렌더링, 하드코딩된 좌표값, 슬라이드 수 고정 로직.

---

## 2. 디렉터리 구조

```
carousel-forge/
├── apps/
│   ├── api/                        # FastAPI 백엔드
│   │   ├── main.py
│   │   ├── routers/                # /styles /topics /carousels /exports /library
│   │   ├── models/                 # SQLModel 정의
│   │   ├── schemas/                # Pydantic 계약
│   │   └── deps.py
│   ├── web/                        # Next.js 프론트
│   └── figma-plugin/               # Figma 플러그인 (TS)
│       ├── manifest.json
│       ├── code.ts                 # 플러그인 샌드박스: 노드 생성
│       └── ui.tsx                  # 세트 선택 UI
├── core/
│   ├── agents/                     # A1~A10 에이전트
│   │   ├── style_forensics.py
│   │   ├── topic_intake.py
│   │   ├── trend_scout.py
│   │   ├── narrative_architect.py
│   │   ├── copysmith.py
│   │   ├── fact_checker.py
│   │   ├── art_director.py
│   │   ├── layout_compositor.py
│   │   ├── quality_gate.py
│   │   └── localizer.py
│   ├── pipeline/
│   │   ├── orchestrator.py         # 상태 머신
│   │   ├── states.py
│   │   └── retry.py                # 폐기·재생성 루프
│   ├── render/
│   │   ├── templates/              # Jinja2 HTML/CSS 레이아웃 템플릿
│   │   ├── html_renderer.py        # Playwright → PNG
│   │   ├── svg_exporter.py         # → 편집 가능 SVG
│   │   └── fonts/                  # 임베드 폰트 (한/중/영)
│   ├── providers/
│   │   ├── image/                  # higgsfield.py, gpt_image.py, base.py
│   │   ├── research/
│   │   └── translate/
│   └── platform/
│       ├── instagram.py            # 규격·제약·캡션 규칙
│       └── xiaohongshu.py
├── config/
│   ├── platforms.yaml              # ★ 플랫폼 규격은 전부 여기. 코드에 하드코딩 금지
│   ├── quality_rules.yaml
│   └── models.yaml
├── storage/
│   ├── assets/{account}/{set_id}/  # bg_01.png, render_01.png ...
│   └── exports/
├── tests/
└── OPEN_QUESTIONS.md
```

---

## 3. 데이터 모델 (SQLModel)

### 3.1 핵심 엔티티

```python
Account          # 운영 계정. 스타일·산출물의 소유 단위
  id, handle, display_name, platform, default_language,
  brand_voice_note, active_style_dna_id, created_at

StyleDNA         # 벤치마크 계정에서 추출한 스타일 자산 (버전 관리됨)
  id, account_id, name, version, source_type,   # screenshots | url | manual
  source_refs (JSON), dna (JSON: StyleDNASchema),
  confidence_score, extracted_at, is_active

TopicBrief       # 정규화된 주제 입력
  id, account_id, raw_input_type,               # document | chat | keyword | proposed
  raw_payload (TEXT), normalized (JSON: TopicSchema),
  proposed_by_system (BOOL), trend_score, created_at

CarouselSet      # 캐러셀 1세트 = 게시물 1개
  id, account_id, style_dna_id, topic_brief_id,
  platform, language, slide_count, status,      # draft|generating|qa|ready|published|archived
  caption (JSON: CaptionSchema), hashtags (JSON),
  quality_report (JSON), fact_report (JSON),
  parent_set_id,                                # 번역/변주 시 원본 참조
  variant_type,                                 # original | translation | restyle
  created_at, updated_at

Slide            # 캐러셀 낱장
  id, set_id, index, role,                      # hook|context|point|proof|example|cta
  layout_template,                              # 템플릿 ID
  background_asset_id, copy_blocks (JSON: List[CopyBlock]),
  render_asset_id, svg_path, notes

Asset            # 생성/렌더된 모든 파일
  id, set_id, kind,                             # background | render | export_svg | export_zip
  path, width, height, mime, provider,
  generation_prompt (TEXT), seed, is_discarded, discard_reason

FactCheck        # 주장 단위 검증 기록
  id, set_id, slide_index, claim, verdict,      # verified|unverified|disputed|false
  sources (JSON), checked_at

GenerationLog    # 폐기·재생성 전부 기록 (품질 추적용)
  id, set_id, stage, attempt, verdict, reason, cost, duration_ms
```

### 3.2 StyleDNA 스키마 — 이 프로그램의 심장

스타일 벤치마킹의 성패는 **"무엇을 추출할지"의 해상도**에 달려 있다. 아래 스키마를 정확히 구현하라. 필드를 임의로 줄이지 말 것.

```jsonc
{
  "identity": {
    "archetype": "editorial-minimal | meme-chaotic | infographic-dense | lifestyle-warm | luxury-clean | zine-collage",
    "one_line": "이 계정을 한 문장으로",
    "target_reader": "누가 이걸 저장하는가"
  },

  "visual": {
    "palette": {
      "primary": ["#RRGGBB"], "accent": ["#RRGGBB"],
      "background": ["#RRGGBB"], "text": ["#RRGGBB"],
      "usage_ratio": { "bg": 0.6, "primary": 0.25, "accent": 0.15 }
    },
    "typography": {
      "headline": { "family": "", "weight": 700, "size_ratio": 0.085,
                    "letter_spacing_em": -0.02, "line_height": 1.15,
                    "case": "as-is | upper | lower" },
      "body":     { "family": "", "weight": 400, "size_ratio": 0.038, "line_height": 1.6 },
      "accent":   { "family": "", "weight": 500, "size_ratio": 0.028 },
      "korean_font": "", "chinese_font": "", "latin_font": "",
      "mixed_script_rule": "한중영 혼용 시 폰트 폴백 순서"
    },
    "layout": {
      "safe_margin_ratio": 0.08,
      "text_zone": "top | center | bottom | split | full-bleed",
      "text_block_max_lines": 4,
      "alignment": "left | center | justified",
      "grid": "single | two-column | card-stack",
      "decorations": ["underline-highlight", "number-badge", "quote-mark", "divider-rule"]
    },
    "imagery": {
      "type_mix": { "photo": 0.6, "illustration": 0.2, "solid_or_gradient": 0.2 },
      "treatment": ["film-grain", "desaturated", "high-contrast", "warm-shift", "duotone"],
      "grain_intensity": 0.0,
      "subject_rules": "인물 등장 여부, 손/제품 등장 방식, 크롭 습관",
      "overlay": { "type": "scrim | gradient | none", "opacity": 0.35 }
    }
  },

  "structure": {
    "slide_count_range": [5, 10],
    "slide_count_mode": 7,
    "hook_type": "question | number-promise | contrarian | pain-point | curiosity-gap | result-first",
    "narrative_pattern": "problem-solution | listicle | story-arc | comparison | tutorial | myth-bust",
    "slide_roles_sequence": ["hook", "context", "point", "point", "point", "proof", "cta"],
    "cta_type": "save | share | comment-keyword | link-in-bio | follow",
    "cover_rule": "커버 1장에 정보를 얼마나 싣는가 (title-only | title+sub | title+sub+badge)"
  },

  "copy": {
    "language": "ko | zh | en",
    "register": "반말 | 존댓말 | 해요체 | 중국어 구어체",
    "sentence_length_avg": 18,
    "headline_char_limit": 22,
    "body_char_limit_per_slide": 80,
    "emoji_density": 0.0,
    "emoji_palette": ["✨", "🔖"],
    "punctuation_habits": "말줄임표·느낌표·줄바꿈 패턴",
    "signature_phrases": ["반복되는 구문"],
    "forbidden_words": ["이 계정이 절대 안 쓰는 말"]
  },

  "caption": {
    "length_range": [150, 600],
    "first_line_rule": "첫 줄 훅 공식 (IG는 첫 125자가 접힘 전 노출)",
    "structure": ["hook", "body", "line_break", "cta", "hashtag_block"],
    "hashtag_strategy": {
      "count": 12,
      "mix": { "broad": 3, "niche": 6, "branded": 2, "community": 1 },
      "placement": "inline | end | first-comment"
    }
  },

  "evidence": {
    "sampled_posts": 12,
    "notes": "추출 근거 메모",
    "low_confidence_fields": ["샘플 부족으로 추정한 필드 목록"]
  }
}
```

**추출 규칙**:
- 최소 6개, 권장 12개 이상의 게시물 샘플에서 추출한다. 샘플이 6개 미만이면 `confidence_score < 0.6`으로 표기하고 사용자에게 경고한다.
- 색상은 눈대중이 아니라 **실제 픽셀 샘플링**으로 뽑는다(k-means 클러스터링, k=6).
- 폰트는 정확 식별이 어려우므로 **"유사 계열 + 사용 가능한 대체 폰트"** 쌍으로 저장한다.
- `size_ratio`는 절대 px가 아니라 **캔버스 짧은 변 대비 비율**로 저장한다. 플랫폼 규격이 바뀌어도 스타일이 유지된다.

---

## 4. 파이프라인 아키텍처

### 4.1 상태 머신

```
INTAKE → STYLE_RESOLVE → RESEARCH → FACTCHECK → ARCHITECT
   → COPY → VISUAL_GEN → COMPOSE → QUALITY_GATE
        ↘ (fail) ──── RETRY ────↗
   → LOCALIZE(optional) → EXPORT → PERSIST → READY
```

각 단계는 순수 함수적으로 설계한다: `(입력 상태, 컨텍스트) → 출력 상태`. 단계는 개별 재실행 가능해야 한다(사용자가 "5번 슬라이드 이미지만 다시" 요청 가능).

### 4.2 에이전트 명세

#### A1. StyleForensics — 스타일 DNA 추출
- **입력**: 벤치마크 계정 피드 스크린샷(다중) 또는 게시물 URL 또는 수동 지정
- **처리**:
  1. 이미지에서 팔레트 추출(k-means), 텍스트 영역 위치·비율 분석
  2. 슬라이드 전개 순서를 읽어 `slide_roles_sequence` 역설계
  3. 본문 캡션 텍스트에서 어미·이모지 밀도·해시태그 전략 통계 산출
  4. LLM에 이미지+텍스트를 함께 넣어 `StyleDNASchema` JSON 강제 출력
- **출력**: `StyleDNA` 레코드 + 사람이 읽는 요약 리포트
- **필수**: 추출 후 **검증 렌더** — 더미 주제로 3장을 뽑아 원본 피드와 나란히 비교 이미지를 생성한다. 사용자가 "닮았다"고 승인해야 `is_active=True`.

#### A2. TopicIntake — 입력 정규화 (멀티모달)
어떤 형태로 들어와도 동일한 `TopicSchema`로 수렴시킨다.

| 입력 타입 | 처리 |
|---|---|
| 문서 (docx/pdf/md/txt) | 파싱 → 섹션 분해 → 핵심 주장 추출 → 캐러셀화 가능한 단위로 재구성 |
| 채팅 대화 | 대화 전체에서 의도·제약·톤 추출. 부족한 슬롯은 **질문 1개만** 되묻는다 |
| 키워드 1~3개 | 확장 리서치로 각도(angle) 3개 제안 → 사용자 선택 |
| URL | 페치 → 요약 → 각도 제안 |
| 시스템 제안 | A3 결과를 그대로 승계 |

```jsonc
// TopicSchema
{
  "title_working": "",
  "angle": "이 주제를 어느 각도로 자를 것인가",
  "audience": "",
  "key_message": "독자가 단 하나만 기억한다면",
  "supporting_points": ["3~7개"],
  "evidence_needed": ["검증이 필요한 주장 목록"],
  "cta_intent": "",
  "constraints": { "must_include": [], "must_avoid": [] },
  "source_fidelity": "strict | flexible"   // 문서 입력 시 원문 충실도
}
```
> `source_fidelity: strict`이면 원문에 없는 사실을 창작하지 않는다. 문서 입력의 기본값은 strict.

#### A3. TrendScout — 선제안 엔진
사용자가 아무것도 안 줘도 먼저 제안한다.

- **데이터 소스**: Google Trends, 네이버 데이터랩, 플랫폼 해시태그 볼륨, 뉴스 API, 샤오홍슈 热榜(가능 시), 계정 과거 성과 데이터
- **스코어링**:
  ```
  score = 0.30·timeliness      # 시의성 (급상승 기울기)
        + 0.25·account_fit     # 계정 아카이브와의 주제 정합성
        + 0.20·utility         # 저장 가치 (how-to/체크리스트/비교)
        + 0.15·volume          # 검색·언급량
        - 0.10·saturation      # 경쟁 포화도 (레드오션 감점)
  ```
- **출력**: 상위 5개 제안. 각 제안은 `{제목안, 각도, 왜 지금인가, 예상 슬라이드 수, 근거 링크 3개}` 포함
- **트리거**: 사용자가 대시보드 진입 시 자동 실행(캐시 6시간), 또는 명시적 요청
- **중복 방지**: 해당 계정의 기존 `CarouselSet`과 의미 유사도(임베딩) 0.85 이상이면 제외

#### A4. NarrativeArchitect — 캐러셀 구조 설계
- StyleDNA의 `narrative_pattern`·`slide_roles_sequence`를 골격으로, 주제의 `supporting_points` 개수에 맞춰 슬라이드 수를 결정
- 각 슬라이드에 `role`, `layout_template`, `단일 메시지`, `필요 비주얼 설명`을 배정
- **1번 슬라이드(커버)에 전체 리소스의 40%를 투입한다.** 훅 후보를 3개 생성해 가장 강한 것을 선택
- **마지막 슬라이드 직전에 "저장 유발 요약본"**을 배치(플랫폼 알고리즘상 저장률이 핵심 지표)

#### A5. CopySmith — 카피 생성
- StyleDNA의 `copy` 블록을 **하드 제약**으로 적용: 글자수 상한, 어미, 이모지 밀도, 금지어
- 슬라이드별로 `CopyBlock[]` 생성:
  ```jsonc
  { "id": "s1_headline", "role": "headline", "text": "",
    "max_chars": 22, "emphasis_spans": [[0,4]], "editable": true }
  ```
- **글자수 초과 시 자동 축약 후 재검증**. 3회 시도 후에도 초과하면 레이아웃 템플릿을 더 큰 텍스트존으로 교체
- 본문 캡션은 별도 생성: 첫 줄 훅 → 본문 → CTA → 해시태그 블록

#### A6. FactChecker — 팩트체크
- `evidence_needed`의 각 주장을 독립적으로 검증(병렬 web_search)
- 판정: `verified` / `unverified` / `disputed` / `false`
- **`false` 또는 `disputed` 판정이 나오면 해당 카피를 자동 폐기하고 A5에 수정 요청**
- `unverified`는 카피에서 단정형을 완화("~이다" → "~라는 분석이 있다")하거나 삭제
- 숫자·통계·연도·인용은 **100% 출처 링크 필수**. 출처 없는 숫자는 파이프라인이 거부한다
- 최종 `fact_report`를 세트에 첨부(사용자가 업로드 전 확인)

#### A7. ArtDirector — 배경 이미지 생성
- **텍스트가 없는 배경만 생성한다.** 프롬프트에 텍스트 렌더링 요청 금지(AI 텍스트 오류의 근원)
- 슬라이드 간 **시각 일관성 잠금**: 동일 팔레트·동일 조명·동일 렌즈감·동일 그레인. 필요 시 Higgsfield Soul/Element로 인물·오브젝트 정체성 고정
- 텍스트가 얹힐 영역은 **저정보 영역(low-detail zone)**으로 확보하도록 프롬프트에 명시
- 프롬프트 구조: `[배경/상황] → [주체] → [핵심 디테일] → [조명/렌즈] → [스타일 제약] → [네거티브]`
- **네거티브 필수 포함**: `text, letters, watermark, logo, hands with wrong fingers, plastic smooth skin, hyperreal glow, oversaturated`

#### A8. LayoutCompositor — 합성
- Jinja2 HTML 템플릿에 배경 이미지 + CopyBlock을 주입
- 폰트는 `@font-face`로 로컬 임베드(웹폰트 네트워크 의존 금지 — 렌더 불일치 원인)
- **오토핏 로직**: 텍스트가 안전영역을 넘으면 → ① 폰트 크기 -5% ② 자간 축소 ③ 줄바꿈 재계산 ④ 그래도 넘치면 카피 축약 요청(A5로 반송)
- **대비 검증**: 텍스트와 배경의 WCAG 대비비 4.5:1 미만이면 스크림 오버레이 자동 삽입 또는 배경 재생성

#### A9. QualityGate — 폐기·재생성 결정권자
`config/quality_rules.yaml`에 정의된 체크리스트를 실행. **하나라도 FAIL이면 통과시키지 않는다.**

```yaml
blocking:                       # 즉시 폐기 → 재생성
  - ai_text_artifact            # 이미지 내 왜곡된 글자·워터마크
  - hand_finger_anomaly         # 손가락 개수·형태 이상
  - identity_drift              # 슬라이드 간 인물 얼굴 불일치
  - plastic_skin                # 하이퍼스무스 피부 (AI 티)
  - morphing_artifact
  - text_overflow               # 안전영역 침범
  - contrast_below_wcag
  - factcheck_false
  - style_deviation             # StyleDNA 팔레트/타이포 이탈 임계 초과
warning:                        # 사용자에게 보고, 진행은 허용
  - hook_strength_low
  - hashtag_saturation
  - caption_length_out_of_range
retry:
  max_attempts_per_slide: 3
  max_attempts_per_set: 8
  on_exhaust: fail_loudly       # 조용히 통과 금지. 실패를 명시 보고
```

- **AI 티 탐지**는 비전 모델에 각 렌더를 넣어 판정한다. "이 이미지가 AI 생성물로 보이는가?"에 YES가 나오면 폐기
- 판정 근거를 반드시 텍스트로 남긴다(`GenerationLog.reason`). 애매하게 통과시키지 말고 구체적 사유를 적는다

#### A10. Localizer — 다국어·플랫폼 변주
- **번역이 아니라 현지화**다. 직역 금지
- 언어별 조판 재계산: 중국어는 한국어보다 같은 의미를 15~30% 짧게 표현 → 폰트 크기·줄바꿈 재산출
- 플랫폼 변환 시 **캔버스 비율이 바뀌므로 레이아웃 재계산 필수**(4:5 → 3:4)
- 원본과 `parent_set_id`로 연결하고 `variant_type='translation'`으로 기록
- 해시태그는 재번역이 아니라 **해당 언어권에서 실제 쓰이는 태그로 재조사**

---

## 5. 플랫폼 규격 (config/platforms.yaml)

> 규격은 변한다. **반드시 설정 파일로 분리**하고 코드는 이 파일만 읽는다. 빌드 시점에 최신값을 재확인하는 검증 스크립트를 포함하라.

```yaml
instagram:
  canvas: { width: 1080, height: 1350, ratio: "4:5" }   # 2026 기준 피드 기본 세로형
  alt_canvas:
    square: { width: 1080, height: 1080, ratio: "1:1" }
  max_slides: 20
  caption_max_chars: 2200
  caption_fold_at: 125            # 이 지점 전에 훅이 끝나야 함
  hashtag_max: 30
  hashtag_recommended: 8-15
  safe_margin_px: 90
  export_format: ["jpg", "png"]
  quality: 95

xiaohongshu:
  canvas: { width: 1080, height: 1440, ratio: "3:4" }   # 피드 노출 면적 최대
  max_slides: 18
  title_max_chars: 20             # ★ 제목 20자 제한 — 커버 카피 설계의 핵심 제약
  body_max_chars: 1000
  topic_tag_max: 10
  cover_info_density: high        # IG 대비 커버에 정보를 더 싣는 문화
  emoji_density: high
  safe_margin_px: 96
```

**플랫폼 문화 차이 (코드 주석이 아니라 프롬프트에 반영할 것)**:
- 인스타그램: 여백·절제·비주얼 우선. 커버는 훅 한 문장.
- 샤오홍슈: 정보 밀도 우선. 커버에 제목+부제+뱃지+포인트까지 싣는다. 이모지·색상 대비 강하게. 「」·【】 괄호 장식 관용적.

---

## 6. Figma 편집 가능성 — 구현 상세 (가장 중요한 기술 요구사항)

사용자는 Figma에서 결과물을 수정한다. **텍스트가 이미지에 구워져 있으면 이 프로그램은 실패한 것이다.**

### 6.1 3중 내보내기 전략

내보내기 ZIP 구조:

```
{account}_{set_id}_{platform}_{lang}/
├── 01_upload/                    # 그대로 업로드 (합성 완료)
│   ├── slide_01.jpg ... slide_09.jpg
├── 02_figma/                     # 편집용
│   ├── slide_01.svg              # 배경 <image> + 편집 가능 <text>
│   ├── backgrounds/
│   │   └── bg_01.png             # 텍스트 없는 배경 원본
│   └── manifest.json             # 플러그인 입력 (좌표·스타일 전체)
├── 03_copy/
│   ├── overlay_copy.txt          # 슬라이드별 오버레이 카피 (복붙용)
│   ├── caption.txt               # 본문
│   ├── hashtags.txt
│   └── copy.json                 # 구조화 버전
├── 04_reference/
│   ├── fact_report.md            # 출처·검증 결과
│   ├── style_dna.json
│   └── fonts/                    # 사용 폰트 (라이선스 확인 후)
└── README.md                     # Figma 반입 방법 안내
```

### 6.2 SVG 내보내기 규칙 (필수 준수)

```
✅ 텍스트는 반드시 <text> / <tspan> 요소로. 절대 <path>로 아웃라인화하지 않는다.
✅ 배경 이미지는 <image xlink:href="..."> 로 참조 (base64 임베드는 파일 비대화 → 옵션)
✅ font-family는 실제 폰트명 명시 + 폴백 체인 (Figma가 로컬 폰트로 매칭)
✅ 레이어 이름은 id 속성으로: id="s01_headline", id="s01_body", id="s01_bg"
✅ 각 슬라이드는 독립 SVG (1080×1350 viewBox)
✅ 그룹핑: <g id="text-layer"> 로 묶어 Figma에서 프레임으로 인식
❌ CSS 클래스 대신 인라인 style 속성 사용 (Figma의 CSS 파싱이 불완전)
❌ filter, mask 남용 금지 (Figma 임포트 시 래스터화됨)
```

### 6.3 Figma 플러그인 (권장 경로)

SVG 드래그앤드롭보다 **자체 플러그인이 압도적으로 우수**하다. 플러그인은 `manifest.json`을 읽어 네이티브 Figma 노드를 생성한다.

```typescript
// apps/figma-plugin/code.ts 핵심 로직
async function buildCarousel(manifest: CarouselManifest) {
  const page = figma.currentPage;
  let x = 0;

  for (const slide of manifest.slides) {
    // 1. 슬라이드 프레임
    const frame = figma.createFrame();
    frame.name = `Slide ${slide.index} — ${slide.role}`;
    frame.resize(manifest.canvas.width, manifest.canvas.height);
    frame.x = x; frame.y = 0;

    // 2. 배경: 이미지 fill (텍스트 없는 원본)
    const img = await figma.createImageAsync(slide.background_url);
    frame.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: img.hash }];

    // 3. 텍스트: 각각 독립 TextNode → 완전 편집 가능
    for (const block of slide.copy_blocks) {
      await figma.loadFontAsync({ family: block.font.family, style: block.font.style });
      const t = figma.createText();
      t.name = block.id;
      t.characters = block.text;
      t.fontSize = block.font.size;
      t.letterSpacing = { unit: 'PERCENT', value: block.font.letter_spacing * 100 };
      t.lineHeight  = { unit: 'PERCENT', value: block.font.line_height * 100 };
      t.fills = [{ type: 'SOLID', color: hexToRgb(block.color) }];
      t.textAlignHorizontal = block.align.toUpperCase();
      t.x = block.x; t.y = block.y;
      t.resize(block.width, t.height);
      t.textAutoResize = 'HEIGHT';
      frame.appendChild(t);
    }

    // 4. 재사용성: 텍스트 스타일을 Figma 로컬 스타일로 등록
    x += manifest.canvas.width + 100;
  }
  figma.viewport.scrollAndZoomIntoView(page.children);
}
```

**manifest.json 계약** (백엔드와 플러그인이 공유하는 JSON Schema로 고정):
```jsonc
{
  "set_id": "", "account": "", "platform": "instagram", "language": "ko",
  "canvas": { "width": 1080, "height": 1350 },
  "fonts_required": [{ "family": "Pretendard", "style": "Bold" }],
  "slides": [{
    "index": 1, "role": "hook",
    "background_url": "https://.../bg_01.png",
    "copy_blocks": [{
      "id": "s01_headline", "role": "headline", "text": "",
      "x": 90, "y": 420, "width": 900, "align": "left",
      "color": "#111111",
      "font": { "family": "Pretendard", "style": "Bold", "size": 92,
                "letter_spacing": -0.02, "line_height": 1.15 }
    }]
  }]
}
```

> **좌표 일치 보장**: `manifest.json`의 좌표는 HTML 렌더링 시 Playwright의 `getBoundingClientRect()`로 실측한 값을 사용한다. 추정값 금지. 이렇게 해야 PNG와 Figma 결과물이 픽셀 단위로 일치한다.

---

## 7. 라이브러리 / DB 축적 요구사항

- 모든 `CarouselSet`은 **계정별로 자동 축적**되며 삭제하지 않는다(`archived` 상태만 존재)
- 폐기된 생성물(`Asset.is_discarded=True`)도 사유와 함께 보존 → 품질 패턴 학습 자산
- 라이브러리 UI 요구사항:
  - 계정 → 플랫폼 → 언어 → 기간 필터
  - 썸네일 그리드 (커버 이미지)
  - 세트 클릭 시: 전체 슬라이드 미리보기 / 카피 복사 / ZIP 재다운로드 / Figma 재전송
  - **"이 세트를 기반으로 새로 만들기"** (리믹스: 주제만 교체 / 언어만 교체 / 스타일만 교체)
  - 전문 검색(캡션·카피 full-text)
- **성과 피드백 루프**: 게시 후 저장수·도달·댓글을 수동 입력하거나 API로 수집 → `TrendScout`의 `account_fit` 스코어링과 `StyleDNA` 개선에 반영

---

## 8. API 엔드포인트

```
POST   /accounts
POST   /styles/extract              # 스크린샷/URL → StyleDNA (비동기 job)
GET    /styles/{id}/preview         # 검증 렌더 3장
POST   /styles/{id}/activate

POST   /topics/ingest               # 문서/채팅/키워드/URL 통합 엔드포인트
GET    /topics/proposals?account_id # TrendScout 선제안 5개

POST   /carousels                   # {account_id, style_dna_id, topic, platform, language}
GET    /carousels/{id}              # 상태 + 진행 스트리밍(SSE)
POST   /carousels/{id}/regenerate   # {scope: "set"|"slide", slide_index, stage}
POST   /carousels/{id}/localize     # {target_language, target_platform}
POST   /carousels/{id}/approve

GET    /exports/{set_id}/zip
GET    /exports/{set_id}/manifest   # Figma 플러그인이 호출
GET    /exports/{set_id}/svg/{idx}

GET    /library?account_id&platform&lang&q&from&to
POST   /library/{set_id}/remix
POST   /library/{set_id}/metrics    # 성과 입력
```

---

## 9. 구축 단계 (마일스톤)

에이전트는 아래 순서로 구현하고, **각 마일스톤 종료 시 실행 가능한 상태**를 유지한다.

| M | 범위 | 완료 기준 (Definition of Done) |
|---|---|---|
| **M0** | 스캐폴딩·DB 스키마·config·JSON Schema → Pydantic/TS 타입 생성 | `alembic upgrade head` 통과, 타입 생성 스크립트 동작 |
| **M1** | 렌더 파이프라인 (HTML 템플릿 → PNG + SVG + manifest) | 하드코딩 더미 데이터로 9장 캐러셀 PNG/SVG 출력. **SVG를 Figma에 넣었을 때 텍스트가 편집 가능**함을 육안 확인 |
| **M2** | A2 TopicIntake + A4 Architect + A5 CopySmith | 키워드 1개 → 슬라이드 구조 + 카피 JSON 산출 |
| **M3** | A1 StyleForensics | 벤치마크 스크린샷 6장 → StyleDNA JSON + 검증 렌더 |
| **M4** | A7 ArtDirector + A8 Compositor + A9 QualityGate | 스타일+주제 → 완성 캐러셀 1세트. 폐기·재생성 루프 동작 |
| **M5** | A6 FactChecker + A3 TrendScout | 출처 링크 포함 fact_report 생성, 선제안 5개 노출 |
| **M6** | Figma 플러그인 | manifest → Figma 프레임 자동 생성, 텍스트 노드 편집 가능 |
| **M7** | A10 Localizer + 샤오홍슈 어댑터 | 한국어 IG 세트 → 중국어 샤오홍슈 세트 변환 |
| **M8** | 라이브러리 UI + 리믹스 + 성과 피드백 | 축적·열람·재다운로드·리믹스 동작 |

---

## 10. 절대 규칙 (에이전트가 위반하면 안 되는 것)

1. **텍스트를 이미지에 굽지 않는다.** 배경과 텍스트는 항상 분리 보관. 합성본은 파생물일 뿐이다.
2. **플랫폼 규격을 코드에 하드코딩하지 않는다.** 전부 `config/platforms.yaml`.
3. **좌표를 추정하지 않는다.** Playwright 실측값만 사용.
4. **출처 없는 숫자·통계·인용을 출력하지 않는다.** 팩트체크 미통과분은 파이프라인이 거부한다.
5. **AI 생성 텍스트를 이미지 프롬프트에 넣지 않는다.** 글자는 항상 렌더 레이어에서 처리.
6. **품질 미달을 통과시키지 않는다.** "완료"는 성공이 아니다. 기준 미달이면 폐기·재생성하고, 재시도 소진 시 명시적으로 실패를 보고한다. 애매한 결과물을 넘기지 말고 솔직한 품질 피드백을 남긴다.
7. **AI 티는 제거 대상이다.** 하이퍼스무스 피부, 모핑, 손가락·문자 오류, 과채도 광택을 탐지하면 폐기한다. 실사 질감·필름 그레인·자연광 레퍼런스를 기본값으로 둔다.
8. **스타일 DNA를 임의로 해석하지 않는다.** 팔레트·타이포·글자수는 하드 제약이다. 이탈 시 QualityGate가 차단한다.
9. **모든 생성물은 DB에 남긴다.** 폐기본 포함.
10. **폰트 라이선스를 확인한다.** 상업적 사용 가능 폰트만 임베드(Pretendard, 노토 산스 KR/SC 등).

---

## 11. 초기 착수 명령 (Claude Code에 그대로 입력)

```
이 문서(CAROUSEL_FORGE_BUILD_SPEC.md)를 읽고 M0와 M1을 구현하라.

M0: 섹션 2의 디렉터리 구조를 생성하고, 섹션 3의 SQLModel 스키마와
    섹션 5의 config/platforms.yaml, 섹션 3.2의 StyleDNA JSON Schema를 작성한다.
    JSON Schema에서 Pydantic 모델과 TypeScript 타입을 생성하는 스크립트를 포함한다.

M1: 렌더 파이프라인을 구현한다.
    - Jinja2 HTML 템플릿 3종 (hook / point / cta 레이아웃)
    - Playwright로 1080x1350 PNG 렌더
    - 동일 템플릿에서 편집 가능 SVG 추출 (섹션 6.2 규칙 엄수)
    - getBoundingClientRect() 실측 좌표로 manifest.json 생성
    - 더미 데이터 9장으로 end-to-end 검증

완료 후 다음을 보고하라:
1. 생성된 SVG를 Figma에 임포트했을 때 텍스트가 편집 가능한지 검증하는 방법
2. PNG와 manifest 좌표가 일치하는지 확인한 결과
3. OPEN_QUESTIONS.md에 기록된 미결 사항
```

---

## 부록 A. 권장 폰트 세트

| 용도 | 한국어 | 중국어(간체) | 영문 |
|---|---|---|---|
| 헤드라인 | Pretendard Bold / 에스코어드림 | 思源黑体 Bold (Noto Sans SC) | Inter / Archivo |
| 본문 | Pretendard Regular | Noto Sans SC Regular | Inter |
| 세리프 무드 | 나눔명조 / 리디바탕 | 思源宋体 (Noto Serif SC) | Instrument Serif |

## 부록 B. 슬라이드 role 정의

| role | 목적 | 카피 밀도 |
|---|---|---|
| `hook` | 스크롤 정지. 단 하나의 강력한 문장 | 최소 |
| `context` | 왜 이게 문제인가 | 낮음 |
| `point` | 핵심 주장 1개 | 중간 |
| `proof` | 데이터·사례·출처 | 중간~높음 |
| `example` | 구체적 적용 예시 | 중간 |
| `summary` | 저장 유발 요약표 | 높음 |
| `cta` | 행동 유도 | 최소 |
