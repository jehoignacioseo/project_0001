# Shorts pipeline

촬영 원본 → 쇼츠(1080x1920) + 롱폼(1920x1080) 자동 편집 → 유튜브 업로드 → 지표 수집.

```
python3 ingest.py  <raw_folder> --out ../work/<episode_id>   # 클립 분석 + 프레임 시트
#   (편집자가 clips.json / frames/*.jpg 를 보고 episode.json 을 씀)
python3 render.py  ../work/<episode_id>/episode.json          # --shorts / --longform
python3 upload.py  <mp4> --title "..." --description-file d.txt --privacy private --shorts
python3 stats.py                                              # work/stats.csv, channel.csv 갱신
python3 make_sample.py                                        # 합성 테스트 클립 생성
```

- 자막: PIL로 PNG 렌더(한글·영문·컬러 이모지), 0.1초 팝 애니메이션. 스타일 pop / shout / whisper / price / note.
- 오버레이: Day 배지, 진행 바(#n/total), 점수판(맛·가성비·재구매), 엔드카드(NEXT + CTA), 롱폼 타이틀카드.
- 오디오: 원본 소리 유지, loudnorm -16 LUFS, 오프닝 팝 효과음 합성.
- 세로 원본 → 롱폼은 블러 배경 필. 가로 원본 → 쇼츠는 센터 크롭.
- 업로드 자격 증명은 환경 변수 YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN. 채팅에 넣지 않음.
- 폰트: NanumSquareRound Bold, Noto Sans CJK KR Bold, Noto Color Emoji (apt: fonts-nanum, fonts-noto-cjk).
