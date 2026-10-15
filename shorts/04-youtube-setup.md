# 유튜브 채널·업로드 자동화 설정 (사용자가 1회만 하면 되는 것)

## A. 채널 개설 (5분)
1. 구글 계정으로 youtube.com 로그인 → 프로필 → "채널 만들기".
2. 채널명: 영어 우선 (예: Seoul Food Diary). 핸들 @seoulfooddiary 확보.
3. 설정 → 채널 → 기본 정보: 거주 국가 대한민국, 키워드 "korean food, convenience store, street food, seoul".
4. 전화 인증(고급 기능 해제): 썸네일 업로드·15분 이상 영상에 필요. 지금 해두는 게 좋음.
5. 배너·프로필 이미지는 제가 만들어 드림(채널명 확정 후).

## B. YouTube Data API 자동 업로드 (15분, 한 번만)
1. console.cloud.google.com → 새 프로젝트 (이름 자유).
2. "API 및 서비스 → 라이브러리" → **YouTube Data API v3** 사용 설정.
3. "OAuth 동의 화면" → 외부(External) → 앱 이름·이메일 입력 → 범위에 `https://www.googleapis.com/auth/youtube.upload` 와 `https://www.googleapis.com/auth/youtube.readonly` 추가 → 테스트 사용자에 본인 이메일 추가.
4. **게시 상태를 "프로덕션"으로 전환**(미검증 경고가 떠도 본인 계정은 사용 가능). 테스트 상태로 두면 토큰이 7일마다 만료됨.
5. "사용자 인증 정보" → OAuth 클라이언트 ID → 유형 **웹 애플리케이션** → 승인된 리디렉션 URI에 `https://developers.google.com/oauthplayground` 추가 → 클라이언트 ID / 보안 비밀 확보.
6. developers.google.com/oauthplayground → 오른쪽 톱니 → "Use your own OAuth credentials" 체크 → ID/비밀 입력 → 왼쪽에서 YouTube Data API v3의 `youtube.upload`, `youtube.readonly` 선택 → Authorize → 본인 계정 승인 → "Exchange authorization code for tokens" → **Refresh token** 복사.
7. 세 값을 **이 클라우드 환경의 환경 설정(세션 제목줄의 환경 메뉴 → Edit → Network secrets 또는 환경 변수)** 에 저장. 채팅에 붙여넣지 말 것.
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`
   새 세션부터 제가 읽어서 업로드·지표 수집을 합니다.

## C. 알아둘 제약
- 구글의 API 규정 심사(YouTube API Services compliance audit)를 통과하기 전에는 **API로 올린 영상이 비공개로 올라갈 수 있음**. 대응: 제가 비공개로 올리고 제목·설명·썸네일까지 채워 두면, 사용자는 YouTube Studio에서 "공개"로 바꾸기만 하면 됨(하루 30초). 심사 신청은 제가 양식을 준비해 드리고 사용자가 제출(보통 1~3주).
- 업로드 1건당 API 할당량 1,600 유닛, 일일 기본 10,000 → 하루 6편까지. 우리 계획(1~2편)엔 충분.
- Google Drive는 이미 연결돼 있어 촬영 원본 수신엔 추가 설정 불필요.
