# 샘플 #02 · mifarsoul 캡슐 스킨케어 (K-뷰티 엑스포 부스)

입력: 촬영본 10클립(IMG_1422–1431.mov, 1080×1920 HDR, 4–7초) → 완성본 48.6초 (본편 46.4초 + 엔드카드).

| 플랫폼 | 링크 |
|---|---|
| TikTok | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/abe8d503-e6b9-4ccc-a62a-6ad72c9febc2.mp4 |
| YouTube Shorts | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/16110bd1-5409-4ce6-8a2a-b1d89576a9fb.mp4 |
| Instagram Reels | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/38455329-3e79-4c02-9932-c149155926c3.mp4 |
| 커버 | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/c7f25fe2-f5db-423b-b225-a613d537f4d1.jpg |

## 구성
- 12컷 (촬영 10 + 공식 이미지 2), 평균 컷 길이 3.9초, 프레임 정지 0.9초.
- 훅: "A pad shaped like your face?" — 핀셋으로 타원형 패드를 들어 올리는 컷 + 상단 타이틀 밴드.
- 정보 카드 6장: 브랜드 · Super Fluid Sunshell(SPF50+ PA++++, $36) · Soothing Gel Pad(100% Tencel, 타원형) · Collagen Spicule Pad · 가격($36 / $38, $65 이상 무료배송) · 판정(신규 브랜드, 리뷰 없음).
- 내레이션: edge-tts `en-US-AvaMultilingualNeural` +18%, 단어 단위 카라오케 자막, 음악 `music_pop` −17 dB 덕킹, −14.6 LUFS.
- 제품 사실은 전부 mifarsoul.com 공식 스토어(Shopify products.json)와 부스 사인 텍스트에서 추출, `products.json`에 출처 기록. 한국 가격·패드 가격은 미확인으로 분리.

## 파일
`footage_annotations.json`(장면 분석) · `products.json`(리서치, 출처) · `episode.json`(컷·내레이션·카드·메타) · `timeline.json`(실제 컷 길이) · `qa.json`(27 pass / 1 warn / 0 fail)

## 이번 샘플에서 파이프라인에 들어간 개선
- 내레이션이 컷보다 길면 `in` 앞쪽의 미사용 촬영분을 먼저 당겨 쓰고, 그래도 모자랄 때만 프레임을 정지 (`render.fit_segments`). 1차 렌더 5.6초 정지 → 0.9초.
- 내레이션 1줄 = 8–11단어로 제한(컷당 2.5–4.5초)해 60초→48초로 밀도 확보.
- 트루피크 여유 확대(limiter 0.7) — AAC 인코딩 후에도 −1 dBTP 이하 유지.
