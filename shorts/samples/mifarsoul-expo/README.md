# 샘플 #02 · mifarsoul 캡슐 스킨케어 (K-뷰티 엑스포 부스)

입력: 촬영본 10클립(IMG_1422–1431.mov, 1080×1920 HDR, 4–7초) → 완성본 47.6초 (본편 45.4초 + 엔드카드) · v5: AI 모델 스튜디오 사용컷 삽입.

| 플랫폼 | 링크 |
|---|---|
| TikTok | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/8a2945f8-82c5-47d1-a2f3-c59d265aa1aa.mp4 |
| YouTube Shorts | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/d8a5d0e9-2bc5-4b91-b74c-5e4a21a06231.mp4 |
| Instagram Reels | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/67ed5540-a669-4413-8bd4-2ac8f81d2d03.mp4 |
| 커버 | https://d2ol7oe51mr4n9.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/46ac7280-c584-4c24-8fcd-7bbd2e424884.jpg |

## 구성
- 13컷 (촬영 10 + 공식 이미지 2 + AI 모델 스튜디오 사용컷 1), 평균 컷 길이 3.5초, 프레임 정지 0.1초.
- **AI 모델 사용컷 (18.0–21.2초)**: 사용자가 준 6표정 레퍼런스 보드 + 촬영본(IMG_1425)의 실제 오렌지 쉘 프레임을 레퍼런스로 `gpt_image_2_5`가 생성한 바스트 샷. 타원 젤패드를 볼에 올린 장면, 화면에 'AI model · studio shot' 라벨, 메타데이터에 AI 생성 고지. 이미지: https://d8j0ntlcm91z4.cloudfront.net/user_3AC7Rg7Ljfg3Zx6KpQgWCxOzWOe/hf_20261017_225130_dbf2e0b9-77b7-4584-b7c4-66c6911e0470.png
- 훅: "A pad shaped like your face?" — 핀셋으로 타원형 패드를 들어 올리는 컷 + 상단 타이틀 밴드.
- 정보 카드 6장: 브랜드 · Super Fluid Sunshell(SPF50+ PA++++, $36) · Soothing Gel Pad(100% Tencel, 타원형) · Collagen Spicule Pad · 가격($36 / $38, $65 이상 무료배송) · 판정(신규 브랜드, 리뷰 없음).
- 내레이션: edge-tts `en-US-AvaMultilingualNeural` +30% (약 1.3배), 단어 단위 카라오케 자막.
- 음악: `music_punch` 126 BPM (레이어드 킥 + 스네어/클랩, 16분 하이햇, 오프비트 스탭, 옥타브 바운스 베이스, 4마디마다 스네어 필) −15 dB, 보이스 아래 사이드체인 덕킹. 최종 −14.6 LUFS / −1.6 dBTP.
- 제품 사실은 전부 mifarsoul.com 공식 스토어(Shopify products.json)와 부스 사인 텍스트에서 추출, `products.json`에 출처 기록. 한국 가격·패드 가격은 미확인으로 분리.

## 파일
`footage_annotations.json`(장면 분석) · `products.json`(리서치, 출처) · `episode.json`(컷·내레이션·카드·메타) · `timeline.json`(실제 컷 길이) · `qa.json`(28 pass / 0 warn / 0 fail)

## 이번 샘플에서 파이프라인에 들어간 개선
- 내레이션이 컷보다 길면 `in` 앞쪽의 미사용 촬영분을 먼저 당겨 쓰고, 그래도 모자랄 때만 프레임을 정지 (`render.fit_segments`). 1차 렌더 5.6초 정지 → 0.9초.
- 내레이션 1줄 = 8–11단어로 제한(컷당 2.5–4.5초)해 60초→48초로 밀도 확보.
- 트루피크 여유 확대(limiter 0.7) — AAC 인코딩 후에도 −1 dBTP 이하 유지.
- v5: 에피소드 스키마의 image 세그먼트를 그대로 써서 AI 생성 사용컷을 삽입(라벨·고지 포함). 이전 v4 링크: TikTok `de266630…`, Shorts `2364b072…`, Reels `d9d6d588…`.
- v4: `audio_assets.punch_beat` 추가(기본 음악 베드로 교체), 보이스 기본 속도 +30%, 플레이북 사운드 규칙 갱신. 이전 v3(108 BPM, +18%) 링크: TikTok `abe8d503…`, Shorts `16110bd1…`, Reels `38455329…`.
