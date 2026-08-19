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
| M2~M8 | 에이전트·Figma 플러그인·라이브러리 UI | ⬜ 미착수 |

구현된 에이전트는 A2·A4·A5 셋이다. 나머지(A1·A3·A6~A10)는 클래스와 단계만
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
3. **육안 — Figma.** `04_reference/fonts/`의 폰트를 설치한 뒤
   `02_figma/slide_01.svg`를 Figma 캔버스로 끌어다 놓고, 텍스트를 더블클릭한다.
   커서가 들어가 글자를 고칠 수 있으면 통과. 벡터 도형(Vector)으로 잡히면 실패다.

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
