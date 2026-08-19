# Carousel Forge

> 스타일(벤치마크 계정 DNA) × 주제 → 인스타그램/샤오홍슈에 즉시 업로드 가능한
> 캐러셀 완성본 → Figma 편집 가능 형태로 내보내기 → 계정별 DB 축적.

사양 원본은 `CAROUSEL_FORGE_BUILD_SPEC.md`다. 이 문서는 **지금 무엇이 돌아가는지**를
적는다.

## 현재 상태

| M | 범위 | 상태 |
|---|---|---|
| **M0** | 스캐폴딩·DB 스키마·config·타입 생성 | ✅ 완료 |
| **M1** | 렌더 파이프라인 (HTML → PNG + SVG + manifest) | ✅ 완료 |
| **M2** | A2 TopicIntake + A4 Architect + A5 CopySmith | ✅ 완료 |
| **M3** | A1 StyleForensics (스크린샷 → StyleDNA + 검증 렌더) | ✅ 완료 |
| **M4** | A7 ArtDirector + A8 Compositor + A9 QualityGate + 폐기·재생성 루프 | ✅ 완료 |
| **M5** | A6 FactChecker (출처 링크 포함 fact_report) | ✅ 완료 · A3 TrendScout는 미착수 |
| **M6** | Figma 플러그인 (manifest → 편집 가능한 프레임) | ✅ 완료 |
| M7 | A10 Localizer + 샤오홍슈 어댑터 | ⬜ 미착수 |
| M8 | 라이브러리 UI + 리믹스 + 성과 피드백 | ⬜ 미착수 |

구현된 에이전트는 A1·A2·A4·A5·A6·A7·A8·A9 여덟이다. 나머지(A3·A10)는 클래스와 단계만
정의돼 있고 `run`은 `NotImplementedError`를 낸다. API도 해당 엔드포인트에서 501을
낸다. **미구현을 빈 결과로 감추지 않는다.**

## 빠른 시작

```bash
cd carousel-forge
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# DB
.venv/bin/alembic upgrade head

# 스키마 → Pydantic + TypeScript
.venv/bin/python scripts/codegen.py

# 플랫폼 규격 검증
.venv/bin/python scripts/validate_platforms.py

# M1 end-to-end: 더미 9장 → PNG + SVG + manifest
.venv/bin/python scripts/make_dummy_backgrounds.py
.venv/bin/python scripts/demo_render.py

# M2 end-to-end: 키워드 1개 → 구조 + 카피 JSON (실제 Claude 호출)
export ANTHROPIC_API_KEY=...
.venv/bin/python scripts/demo_m2.py --keyword 러닝입문
.venv/bin/python scripts/demo_m2.py --keyword 러닝입문 --resume --render   # M1 렌더까지

# M3 end-to-end: 벤치마크 피드 → StyleDNA + 검증 렌더 + 정답 대조
.venv/bin/python scripts/make_benchmark_feed.py
.venv/bin/python scripts/demo_m3.py

# M4 end-to-end: 배경 생성 → 합성 → 품질 게이트 → 폐기·재생성
.venv/bin/python scripts/demo_m4.py --keyword 러닝입문 --from-briefs
.venv/bin/python scripts/demo_m4.py --keyword 러닝입문 --from-briefs --fail-slides 3  # 재생성 루프 확인

# M5: 웹 검색으로 주장 검증 → 출처 링크 포함 fact_report
.venv/bin/python scripts/demo_m5.py

# M6 Figma 플러그인
cd apps/figma-plugin && npm install && npm run build && npm test

# PNG과 SVG가 정말 같은 좌표에서 나왔는지 픽셀로 대조
.venv/bin/python scripts/verify_render.py storage/exports/deskreset_demo0001_instagram_ko

# 테스트 (브라우저 없이 돌리려면 -m "not browser")
.venv/bin/python -m pytest
```

API를 띄우려면:

```bash
.venv/bin/uvicorn apps.api.main:app --reload
# http://127.0.0.1:8000/docs
```

## 설계에서 물러서지 않는 세 가지

**1. 텍스트를 이미지에 굽지 않는다.**
배경 레이어와 텍스트 레이어는 끝까지 분리돼 있다. 업로드용 PNG/JPG는 파생물일 뿐이고,
`02_figma/backgrounds/`에는 글자 없는 배경 원본이 그대로 남는다. 텍스트를
래스터화하는 코드 경로는 존재하지 않는다.

**2. 단일 소스 → 다중 출력.**
`RenderSet` 하나에서 PNG / SVG / manifest.json / TXT가 **한 번의 렌더**로 파생된다.
출력물끼리 어긋날 방법이 없다.

**3. 좌표를 추정하지 않는다.**
manifest와 SVG의 모든 좌표는 Playwright가 페이지 안에서 잰 값이다
(`core/render/measure.js`). 베이스라인조차 폰트 메트릭으로 계산하지 않고,
높이 0짜리 inline-block을 같은 줄에 놓아 **잰다**.

**4. 스타일도 추정하지 않는다.**
색은 픽셀 k-means에서, 텍스트 위치·여백·정렬은 경사 기하에서, 말투·이모지 밀도·
해시태그 전략은 캡션 통계에서 **센다**(`core/agents/forensics/`). 모델은 잰 값을
쥔 채로 세어서는 알 수 없는 것(아키타입·서사 패턴·훅 공식)만 해석하고, 측정 가능한
필드는 모델이 뭐라 답하든 측정값으로 덮어쓴다.

## 렌더 파이프라인

```
RenderSet (배경 참조 + CopyBlock, 분리 상태)
   │
   ├─ Jinja2 템플릿 (hook / point / cta) ─→ HTML
   │
   └─ Playwright(Chromium)
        ├─→ 스크린샷            → 01_upload/slide_NN.jpg
        └─→ measure.js 실측 기하 ─┬─→ 02_figma/slide_NN.svg   <text>/<tspan>
                                 ├─→ 02_figma/manifest.json  Figma 플러그인 계약
                                 └─→ 안전영역 침범 판정
```

`storage/exports/{account}_{set}_{platform}_{lang}/` 구조는 사양 6.1과 같다.

## Figma에서 편집 가능한지 확인하는 법

세 겹으로 확인한다.

1. **자동 — 좌표 대조.** `scripts/demo_render.py`가 manifest의 줄 베이스라인과
   SVG `<tspan>`의 `y`를 대조한다. 어긋나면 실패한다.
2. **자동 — 픽셀 대조.** `scripts/verify_render.py`가 내보낸 SVG를 다시 Chromium으로
   래스터화해 업로드용 이미지와 비교하고, ±1px 이동해봤을 때 더 잘 맞는지 확인한다.
   최적 이동이 `(0,0)`이 아니면 좌표가 밀린 것이다.
3. **자동 — 노드 대조.** M6 플러그인의 테스트가 가짜 Figma API로 노드 생성까지
   돌려, 카피가 벡터가 아니라 TextNode가 되는지·폰트를 글자보다 먼저 불러오는지·
   카피가 하나도 빠지지 않는지 확인한다 (`apps/figma-plugin`, 31개).
4. **육안 — Figma.** `04_reference/fonts/`의 폰트를 설치한 뒤, 플러그인으로
   `02_figma/manifest.json`을 불러오거나 `slide_01.svg`를 캔버스로 끌어다 놓고
   텍스트를 더블클릭한다. 커서가 들어가 글자를 고칠 수 있으면 통과. 벡터
   도형(Vector)으로 잡히면 실패다. **이 단계만은 사람이 한 번 해봐야 한다.**

## 디렉터리

```
apps/api/            FastAPI · SQLModel 정의 · 생성된 Pydantic 계약
apps/web/            Next.js 프론트 (M8)
apps/figma-plugin/   Figma 플러그인 (M6) · 생성된 TypeScript 계약
core/agents/         A1~A10 (M2 이후)
core/pipeline/       상태 머신 · 재시도 예산
core/render/         템플릿 · 렌더러 · SVG · manifest   ← M1의 본체
core/providers/      이미지/리서치/번역 프로바이더 인터페이스
core/platform/       플랫폼별 규칙과 문화 (수치는 config에서)
config/              platforms.yaml · quality_rules.yaml · models.yaml
schemas/             JSON Schema — 백엔드·플러그인 계약의 단일 진실 소스
scripts/             codegen · 검증 · 데모
```

## 정해지지 않은 것

`OPEN_QUESTIONS.md`에 15건을 적어 뒀다. 전부 기본값을 정해 진행했고, 무엇을
바꾸면 되는지도 함께 적었다.

## 팩트체크는 서버측 검색으로 돈다

이 환경은 조직 egress 정책으로 아웃바운드가 막혀 있다. 그래서 A6는 우리 쪽에서
HTTP를 쏘지 않고 **Anthropic 서버에서 도는 `web_search`/`web_fetch`**를 쓴다.
검색이 우리 컨테이너를 거치지 않으므로 네트워크 정책과 무관하게 검증이 된다.

지키는 규칙 셋:

- **주장마다 따로 묻는다.** 한 번에 몰아 물으면 모델이 앞 판정에 뒤 판정을 맞춘다.
- **출처 없이 verified는 없다.** 모델이 verified라고 답해도 검색이 실제로 연 페이지가
  없으면 unverified로 내린다.
- **지어낸 URL은 출처로 세지 않는다.** 모델이 적은 URL을 서버 검색이 실제로 열어 본
  목록과 대조한다. 대조하지 않으면 그럴듯한 주소가 근거로 통과한다.

그리고 `unsourced_claim` 규칙이 카피의 숫자·연도·인용이 검증된 주장으로 덮이는지
센다. 덮이지 않으면 품질 게이트가 폐기한다 (절대 규칙 #4).

### 이 검증이 우리 config에 대해 알려준 것

`scripts/demo_m5.py`를 `platforms.yaml`의 값에 돌린 결과다.

| 값 | 판정 | 근거 |
|---|---|---|
| `instagram.max_slides: 20` | verified | 인스타그램 공식 고객센터 문서 |
| `instagram.caption_max_chars: 2200` | verified | Meta 개발자 문서 |
| `instagram.caption_fold_at: 125` | **unverified** | 2차 출처만 반복, 1차 없음 |
| `xiaohongshu.title_max_chars: 20` | **disputed** | 공식 문서 없고 출처 간 설명이 갈림 |

뒤 둘은 값을 유지하되 확정된 규격으로 취급하지 않는다. `platforms.yaml`의
`_meta.source_check`에 근거와 함께 적어 뒀다.

## 폐기·재생성 루프

품질 게이트가 폐기를 판정하면 통과시키지 않는다. 문제가 생긴 슬라이드만 되감아
새 seed로 다시 만들고, `config/quality_rules.yaml`의 예산이 바닥나면 **명시적으로
실패한다**. 통과 경로만 보고 루프가 돈다고 말할 수 없으므로 데모에 실패 주입
모드(`--fail-slides`)를 두어 되감기·재생성·예산 소진을 실제로 밟는다.

조정에도 순서가 있다. 안전영역을 넘으면 폰트 −5% → 자간 축소 순으로 줄이고
(자간부터 줄이면 글자가 붙어 읽기 어렵다), 그래도 안 들어가면 여기서 카피를
자르지 않고 **A5에 축약을 요청한다**. 대비가 모자라면 스크림을 단계적으로 올리고,
한계까지 올려도 안 되면 **A7에 배경 재생성을 요청한다**.

대비는 팔레트 값이 아니라 **텍스트 뒤에 실제로 깔린 픽셀**로 잰다. 텍스트를 숨기고
한 장 더 찍어 그 위에서 가장 불리한 픽셀을 찾는다 — 평균을 쓰면 밝은 배경에 밝은
글자가 한쪽에서만 겹치는 경우를 놓친다.

## 스타일 추출 정확도

알려진 StyleDNA로 피드를 렌더한 뒤 그것만 보고 다시 추출하는 왕복 검증으로 잰다
(`scripts/make_benchmark_feed.py` → `scripts/demo_m3.py`). 실제 계정 스크린샷은
정답이 없고 남의 저작물이기도 해서, 정답을 아는 피드를 직접 만든다.

샘플 6장 기준 최근 측정:

| 층 | 결과 |
|---|---|
| 측정 (픽셀·기하·통계) | 8/8 — 팔레트 ΔE 0.0 / 0.7 / 0.6, 텍스트존·정렬 일치, 여백 오차 0.022 |
| 해석 (모델 판단) | 6/8 |
| 전체 | 88% |

해석 층에서 어긋난 둘은 벤치마크 피드의 한계에서 온다 — 커버만 렌더해서 본문
텍스트가 없으니 본문 크기를 볼 수 없고, 여백이 넓어 실제보다 미니멀해 보인다
(`OPEN_QUESTIONS.md` 24번).
