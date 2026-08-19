# 임베드 폰트

상업적 사용이 가능한 폰트만 담는다 (절대 규칙 #10). 폰트 파일을 넣었으면
라이선스 사본도 같이 넣는다 — OFL은 재배포 시 사본 동봉을 요구하고,
`04_reference/fonts/`로 나가는 내보내기가 곧 재배포다.

| 패밀리 | 굵기 | 용도 | 라이선스 |
|---|---|---|---|
| Pretendard | Regular / Bold / ExtraBold | 한국어·라틴 | SIL OFL 1.1 |
| Noto Sans SC | Regular / Bold / ExtraBold | 중국어 간체 | SIL OFL 1.1 |

받아오는 방법:

```bash
python scripts/fetch_fonts.py            # ko — Pretendard
python scripts/fetch_fonts.py --set zh   # zh — Noto Sans SC
```

## 왜 통합 subset 파일인가

`@fontsource/noto-sans-sc`는 subset별로 파일이 수백 개로 쪼개져 있다. 웹에서는
필요한 조각만 내려받아 이득이지만, 여기서는 파일을 `@font-face` 하나로 임베드하고
같은 폰트를 Figma에도 설치해야 하므로 **`chinese-simplified` 통합 파일**을 쓴다.
조각난 파일을 쓰면 `unicode-range`가 맞지 않는 글자에서 조용히 폴백으로 떨어지고,
그 순간 실측 좌표와 실제 글자가 갈라진다.

## 굵기 이름을 맞춰 두는 이유

Figma에는 글리프 단위 폴백이 없다. 플러그인이 만드는 TextNode는 `{family, style}`
한 쌍으로 폰트를 고르므로, 중국어 세트의 굵기가 하나라도 비어 있으면 그 역할만
다른 폰트로 잡히거나 두부(□)가 된다. 그래서 Pretendard가 가진 굵기는 Noto Sans SC도
같은 이름으로 갖춘다 (`tests/test_render_model.py`가 이 관계를 지킨다).
