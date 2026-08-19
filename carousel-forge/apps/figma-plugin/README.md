# Carousel Forge — Figma 플러그인

`manifest.json`을 읽어 Figma에 **편집 가능한** 캐러셀을 만든다. 각 카피 블록은
독립 TextNode가 되고, 배경은 프레임의 이미지 fill이 된다.

## 왜 SVG가 아니라 플러그인인가

내보내기에는 두 경로가 들어 있다. 둘의 차이는 하나다 — **문구를 늘렸을 때 무슨
일이 일어나는가.**

| | SVG 드래그앤드롭 | 플러그인 |
|---|---|---|
| 텍스트 편집 | 가능 | 가능 |
| 문구를 늘리면 | 줄마다 `tspan`에 좌표가 박혀 있어 그 줄만 길어진다 | 폭만 고정돼 있어 Figma가 다시 흘린다 |
| 폰트가 없으면 | 조용히 대체되고 줄바꿈이 달라진다 | 무엇이 없는지 알려주고 멈춘다 |
| 강조 구간 | 색이 다른 `tspan` | `setRangeFills` — 편집해도 유지된다 |
| 준비물 | 없음 | 플러그인 설치 |

SVG는 "문구 몇 글자 다듬기"에, 플러그인은 "제대로 편집하기"에 맞다.

## 쓰는 법

```bash
npm install
npm run build      # dist/code.js, dist/ui.html
```

Figma 데스크톱 앱에서 **Plugins → Development → Import plugin from manifest…**
를 고르고 이 폴더의 `manifest.json`을 지정한다.

플러그인을 실행하면 파일 두 가지를 묻는다. 내보내기 폴더의 `02_figma/` 안에 있다.

1. `manifest.json` — 좌표·폰트·카피
2. `backgrounds/` 안의 이미지 전부 — 파일명의 숫자로 슬라이드와 짝짓는다 (`bg_03.png` → 3번)

**폰트를 먼저 설치해야 한다.** `04_reference/fonts/`의 폰트가 시스템에 없으면
플러그인이 무엇이 없는지 알려주고 멈춘다. 대체 폰트로 만들면 줄바꿈과 크기가
원본과 달라지는데, 그 상태로 만들어 두면 나중에 원인을 찾기 어렵다.

## 편집 가능한지 확인하는 법

만들어진 뒤 이것만 보면 된다.

1. 아무 텍스트나 **더블클릭** → 커서가 들어가고 글자를 고칠 수 있으면 통과
2. 오른쪽 패널에 **Text** 속성(폰트·크기·자간·행간)이 뜨면 통과
3. 레이어 이름이 `s01_headline`처럼 보이면 통과

벡터 도형(Vector)으로 잡히거나 패널에 Text 속성이 없으면 실패다 — 그건 텍스트가
아웃라인화됐다는 뜻이고, 이 프로그램의 전제가 무너진 것이다.

## 구조

```
manifest.json      Figma 플러그인 매니페스트 (백엔드의 02_figma/manifest.json과 다른 파일)
build.mjs          esbuild 번들 — Figma 샌드박스는 모듈을 못 읽는다
src/
  carousel.ts      manifest → 노드 사양. Figma를 부르지 않는 순수 변환
  nodes.ts         사양 → 실제 노드. figma 전역을 쓴다
  code.ts          샌드박스 진입점 — UI 메시지 처리
  ui.html          파일 선택 UI
  figma-fake.ts    테스트용 가짜 Figma API
  generated/       JSON Schema에서 생성된 타입 — 손으로 고치지 않는다
```

로직을 `carousel.ts`와 `nodes.ts`로 나눈 이유는 검증 때문이다. Figma 안에서만 돌
수 있는 코드를 "돌려는 봤다"로 남겨 두지 않으려고, 가짜 `figma` 전역을 끼워
노드 생성까지 테스트한다.

```bash
npm run typecheck
npm test           # 31개
```

테스트는 실제 M1 산출물(`tests/fixtures/manifest_demo.json`)을 쓴다. 손으로 만든
예시는 스키마가 바뀌어도 통과해서 계약이 갈라진 걸 못 잡는다.

## 테스트가 잡는 것 / 못 잡는 것

**잡는 것** — 카피 블록이 벡터가 아니라 TextNode가 되는가, 폰트를 글자보다 먼저
불러오는가(순서가 바뀌면 기본 폰트로 들어간다), 카피가 하나도 빠지지 않는가,
좌표를 플러그인이 다시 계산하지 않는가, 강조 구간이 `setRangeFills`로 가는가,
높이를 고정하지 않는가, 오버레이가 잠긴 채 들어가는가.

**못 잡는 것** — 실제 Figma에서 눈으로 보는 것. 가짜 API는 우리가 부르는 것만
받아 적을 뿐 진짜 Figma의 동작을 재현하지 않는다. 위의 "편집 가능한지 확인하는 법"
세 가지는 사람이 한 번 해봐야 한다.

## 계약

`src/generated/`의 타입은 `schemas/carousel_manifest.schema.json`에서 나온다.
백엔드의 Pydantic 모델도 같은 스키마에서 나오므로 둘이 갈라질 수 없다.
스키마를 고쳤으면 저장소 루트에서 재생성한다.

```bash
python scripts/codegen.py
```

플러그인은 `schema_version`이 1이 아니면 읽지 않는다. 모르는 버전을 짐작해서
읽으면 좌표가 어긋난 채로 만들어지고, 그건 조용히 틀린 결과물이 된다.
