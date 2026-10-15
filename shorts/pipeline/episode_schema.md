# episode.json

```json
{
  "id": "S1-05",                       // 파일명 접두
  "series": "S1", "number": 5, "total": 33, "day": 5,
  "title_ko": "뚱바 라떼", "title_en": "Banana Milk Latte",
  "hook": "#5/33 · ...",               // 제목/설명 생성용
  "segments": [                        // 순서대로 이어 붙임
    {"src": "clip2.mp4", "in": 1.0, "out": 4.5, "speed": 1.0,
     "captions": [ {"t": 0.2, "d": 2.0, "text": "...", "style": "pop"} ] }   // t,d는 세그먼트 기준 초
  ],
  "longform_segments": [ ... ],        // 생략 시 segments 재사용(롱폼은 더 길게 잘라 넣는 용도)
  "price": {"krw": 3400, "usd": 2.5},
  "score": {"taste": 8, "value": 9, "again": "YES"},
  "comment": "한 줄 평 (이모지 OK)",
  "score_at": 17.5, "score_duration": 4.0,   // 생략 시 끝에서 7초 전
  "next": "#6 ...", "cta": "..."
}
```
