# apps/figma-plugin — Figma 플러그인 (M6)

아직 착수하지 않았다. 지금 여기 있는 것은 **계약**뿐이다.

- `src/generated/` — `schemas/*.schema.json`에서 생성된 TypeScript 타입.
  손으로 고치지 말고 `python scripts/codegen.py`로 재생성한다.

M6에서 만들 것:

- `manifest.json`(Figma 플러그인 매니페스트 — 백엔드의 `02_figma/manifest.json`과는 다른 파일)
- `code.ts` — `CarouselManifest`를 읽어 슬라이드마다 프레임을 만들고,
  `copy_blocks`를 각각 독립 TextNode로 놓는다. 좌표는 manifest의 실측값을 그대로 쓴다.
- `ui.tsx` — 세트 선택 UI

플러그인 경로가 SVG 드래그앤드롭보다 나은 이유: TextNode에 전체 문자열과 폭을
주므로 Figma가 스스로 줄바꿈한다. SVG는 줄이 `<tspan>`으로 고정돼 있어 문구를
길게 고쳐도 다음 줄로 넘어가지 않는다.
