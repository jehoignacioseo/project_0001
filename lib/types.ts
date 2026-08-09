// 앱 전역에서 쓰는 도메인 타입 정의

/** 소재의 출처 성격 — 뉴스만이 아니라 실제 소비자·인플루언서 목소리까지 구분한다. */
export type SourceKind = 'news' | 'community' | 'influencer' | 'trend' | 'blog';

export interface AppSettings {
  category: string;            // 예: "캠핑 용품", "AI 트렌드", "홈카페"
  keywords: string[];          // 수집에 사용할 검색 키워드
  customFeeds: string[];       // 사용자가 추가한 RSS 피드 URL
  enabledSources: SourceKind[];   // 수집할 소스 종류
  englishKeywords: string[];      // 해외 커뮤니티 검색용 영문 키워드
  subreddits: string[];           // 모니터링할 서브레딧 (예: AsianBeauty)
  youtubeChannels: string[];      // 유튜브 채널 ID 또는 채널 RSS 주소
  trendsGeo: string;              // 구글 트렌드 지역 코드 (KR, US ...)
  brandName: string;           // 계정/브랜드 이름 (콘텐츠 톤에 반영)
  brandTone: string;           // 톤앤매너 설명
  targetAudience: string;      // 타깃 독자 설명
  slideTheme: SlideThemeId;    // 기본 슬라이드 템플릿
  language: string;            // 콘텐츠 언어 (기본 한국어)
  model: string;               // Claude 모델 ID
  anthropicApiKey: string;     // 비어 있으면 env ANTHROPIC_API_KEY 사용
  igAccessToken: string;       // Instagram Graph API 액세스 토큰
  igBusinessId: string;        // Instagram 비즈니스 계정 ID
  publicBaseUrl: string;       // 배포된 앱의 공개 URL (발행 시 이미지 호스팅에 필요)
}

export type SlideThemeId = 'bold' | 'clean' | 'dark' | 'magazine';

export interface SourceItem {
  id: string;
  title: string;
  link: string;
  source: string;          // 매체명
  kind: SourceKind;        // 출처 성격
  publishedAt: string;     // ISO
  snippet: string;
  collectedAt: string;
  // Claude 선별 결과
  viralScore?: number;         // 0~100
  scoreReason?: string;        // 점수 근거
  contentAngle?: string;       // 인스타 콘텐츠화 앵글 제안
  hookIdea?: string;           // 훅(첫 슬라이드) 아이디어
}

export interface Slide {
  role: 'hook' | 'content' | 'cta';
  headline: string;        // 슬라이드 대형 카피
  body: string;            // 보조 텍스트 (없으면 빈 문자열)
  kicker: string;          // 상단 작은 라벨 (없으면 빈 문자열)
  imagePrompt: string;     // (선택) 배경 이미지 생성용 프롬프트
  bgImageUrl?: string;     // 업로드/생성된 배경 이미지 경로
}

export type PostStatus = 'draft' | 'ready' | 'published' | 'failed';

export interface Post {
  id: string;
  createdAt: string;
  updatedAt: string;
  status: PostStatus;
  sourceItem: SourceItem;      // 원 소재
  slides: Slide[];
  caption: string;             // 포스팅 본문
  hashtags: string[];
  theme: SlideThemeId;
  slideImagePaths: string[];   // 렌더링된 PNG 경로 (/uploads/...)
  publishedMediaId?: string;
  publishError?: string;
  revisions: { at: string; feedback: string }[];
}

export interface CarouselDraft {
  slides: Slide[];
  caption: string;
  hashtags: string[];
}
