# K-Beauty Shorts 자동화 (촬영본 → TikTok · Reels · Shorts 완성본)

사람은 **폰으로 찍은 원본 클립만** 폴더에 넣습니다. 나머지는 AI가 합니다.

```
촬영본 폴더 ─▶ ① analyze   장면 분석(컷 감지·키프레임·Claude 비전·음성 전사) → footage.json
            ─▶ ② research  제품 정보 수집(웹검색: 성분·한국가/해외가·올영 랭킹·출시일) → products.json
            ─▶ ③ script    편집 결정(포맷·훅·컷리스트·내레이션·정보카드·CTA·플랫폼 메타) → episode.json
            ─▶ ④ tts       AI 보이스 + 단어 단위 타임스탬프 → vo/
            ─▶ ⑤ render    컷 편집 + 카라오케 자막 + 훅 밴드 + 카드 + SFX/음악 + 라우드니스 → out/*_{tiktok,reels,shorts}.mp4 + 커버
            ─▶ ⑥ qa        자동 검수(규격·길이·라우드니스·훅 타이밍·숫자 출처 추적·의학 표현·메타 길이) → qa.json
            ─▶ ⑦ publish   (선택) YouTube 업로드 / Reels 발행 / TikTok 보관함 업로드
```

## 설치

```bash
pip install -r shorts/kbeauty/requirements.txt       # anthropic, edge-tts, faster-whisper, pillow, numpy, requests
# ffmpeg 6+ (libass·libx264 포함) 필요.  Windows: winget install Gyan.FFmpeg
export ANTHROPIC_API_KEY=sk-ant-...                    # 또는 `ant auth login`
```

선택 환경변수

| 변수 | 용도 |
|---|---|
| `KB_MODEL` | 기본 `claude-opus-5-5` |
| `KB_TTS` / `KB_VOICE` | `edge`(기본, 무료) · `elevenlabs`(`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`) · `mock` |
| `KB_WHISPER` | 촬영본 속 말소리 전사 모델(`small` 기본, 빈 값이면 끔) |
| `KB_LANG` | 내레이션·자막 언어(`en` 기본) |
| `YT_CLIENT_ID` `YT_CLIENT_SECRET` `YT_REFRESH_TOKEN` | YouTube 업로드 (`shorts/04-youtube-setup.md` 참고) |
| `IG_USER_ID` `IG_ACCESS_TOKEN` `KB_PUBLIC_BASE_URL` | Reels 발행(인스타 서버가 mp4를 가져가므로 공개 URL 필요) |
| `TIKTOK_ACCESS_TOKEN` | TikTok Content Posting API(미심사 앱은 "보관함 업로드"까지) |

## 사용

```bash
cd shorts/kbeauty
python3 run.py /path/to/2026-10-16_anua --note "올영 명동점, 아누아 패드 1위 스티커, 19,900원"
python3 run.py /path/to/folder --publish --privacy private      # 렌더 후 바로 업로드
python3 run.py /path/to/folder --from render                     # 특정 단계부터 재실행(episode.json 손수 고친 뒤 등)
python3 run.py /path/to/folder --mock --fast                     # API·네트워크 없이 파이프라인 점검
python3 watch.py --inbox ../inbox --publish                      # 무인 모드: 폴더 떨어지면 자동 처리
```

Windows는 저장소 루트의 `kbeauty-run.bat`에 **클립 폴더를 드래그**하면 됩니다(인자 없이 실행하면 inbox 감시).
폴더 안에 `note.txt`를 두면 `--note` 대신 읽습니다(한 줄이면 충분: "맛/느낌, 가격, 눈에 띈 점").

### 결과물 (`shorts/work/kbeauty/<날짜>_<폴더>/out/`)

- `<id>_tiktok.mp4`, `<id>_reels.mp4`, `<id>_shorts.mp4` — 1080×1920 30fps, -14 LUFS, 엔드카드만 플랫폼별로 다름
- `<id>_cover.jpg` — 썸네일(훅 문구)
- `meta_<platform>.json` — 캡션·해시태그·제목·설명·고정 댓글·대체 훅 3개(Trial Reels / A-B 테스트용)
- `qa.json`, `publish_manifest.json`

### 중간 산출물(사람이 개입하고 싶을 때만)

`footage.json`(장면 분석) → `products.json`(검증된 사실 + 출처 URL, 미검증 항목 분리) → `episode.json`(컷·내레이션·카드).
`episode.json`을 고치고 `--from tts`로 다시 돌리면 그대로 반영됩니다.

## 트렌드/알고리즘 반영 방식

편집 두뇌는 `playbook.md`입니다. 플랫폼이 지금 보상하는 신호(첫 3초 이탈, 완주율 70%, 2~4초마다 패턴 인터럽트, 원본성, AI 보이스
공개, Trial Reels), K뷰티에서 돌아가는 8가지 포맷(리테일 증거·가격 쇼크·성분 설명·텍스처 ASMR·선반 카운트다운·신상 알림·비교·오해 교정),
훅 규칙, 자막 규칙, 정보 무결성 규칙을 담고 있고 매 에피소드 프롬프트에 그대로 들어갑니다.
**트렌드가 바뀌면 코드가 아니라 `playbook.md`만 고치면 됩니다.**

## 안전장치

- 자막·내레이션의 모든 숫자는 `products.json` 또는 촬영본에 보이는 글자에서만 나옵니다(QA가 추적, 없으면 경고).
- 의학적 표현(cures/treats/…)은 QA에서 실패 처리. AI 보이스는 설명란에 명시(YouTube 2026-07 비진정성 정책 대응).
- QA FAIL이면 publish 단계가 실행되지 않습니다.

## 한계 / 다음 단계

- TikTok 직접 게시는 심사된 앱이 필요합니다. 미심사면 보관함(inbox) 업로드 후 앱에서 한 번 탭. 또는 Higgsfield TikTok 커넥터 사용.
- Reels 발행은 mp4 공개 URL이 필요합니다(Vercel/Cloudflare R2 등에 `out/` 동기화 후 `KB_PUBLIC_BASE_URL` 지정).
- 음성 전사(faster-whisper)는 첫 실행 때 모델을 내려받습니다.
