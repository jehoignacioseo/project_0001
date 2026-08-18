# storage

렌더·내보내기 산출물이 쌓이는 곳이다.

```
assets/{account}/{set_id}/   bg_01.png, render_01.png …
exports/{account}_{set}_{platform}_{lang}/
```

파일 자체는 `.gitignore` 대상이다. 보존해야 하는 것은 파일이 아니라 DB 레코드
(`Asset`, `GenerationLog`)이고, 폐기본도 사유와 함께 레코드로 남는다
(절대 규칙 #9). 파일 보존 기간·용량 정책은 아직 정해지지 않았다 —
`OPEN_QUESTIONS.md` 14번.
