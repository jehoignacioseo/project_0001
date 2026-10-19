// Claude 호출용 프롬프트와 JSON 스키마 정의.
// 산출물 품질이 서비스 가치의 전부이므로, 프롬프트에는
// 인스타그램 바이럴 콘텐츠의 판단 기준과 카피라이팅 원칙을 명시한다.

import type { AppSettings, SourceItem, Post } from './types';

// ---------- 1) 소재 바이럴 점수 판정 ----------

export const SCORE_SCHEMA = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          viralScore: { type: 'integer' },
          scoreReason: { type: 'string' },
          contentAngle: { type: 'string' },
          hookIdea: { type: 'string' },
        },
        required: ['id', 'viralScore', 'scoreReason', 'contentAngle', 'hookIdea'],
        additionalProperties: false,
      },
    },
  },
  required: ['results'],
  additionalProperties: false,
} as const;

export function scoreSystemPrompt(s: AppSettings): string {
  return `당신은 인스타그램 비즈니스 계정 콘텐츠 전략가다. "${s.category}" 분야의 정보성 계정을 운영하며, 뉴스·트렌드·제품 소재 중 어떤 것이 인스타그램(피드 캐러셀)에서 조회수와 저장을 만들어낼지 판단한다.

타깃 독자: ${s.targetAudience}
계정 톤: ${s.brandTone}

각 소재에 대해 0~100의 viralScore를 매긴다. 판단 기준:
- 저장 가치: 독자가 "나중에 보려고 저장"할 실용 정보인가 (가장 큰 가중치)
- 훅 가능성: 첫 슬라이드 한 줄로 스크롤을 멈출 수 있는가 (숫자, 반전, 손실 회피, 궁금증)
- 시의성: 지금 올려야 의미 있는 트렌드/뉴스인가
- 공유 동기: 친구를 태그하거나 스토리로 공유할 이유가 있는가
- 타깃 적합도: 위 타깃 독자의 실제 관심사와 맞닿아 있는가
- 시각화 용이성: 캐러셀 슬라이드로 구조화(리스트, 비교, 순위, 단계)하기 좋은가

## 소재 종류별로 다르게 볼 것
소재에는 [뉴스] 외에 [커뮤니티], [인플루언서], [트렌드] 가 섞여 있다. 종류마다 가치가 다르다.

- [뉴스]: 사실과 시의성은 좋지만 보도자료를 그대로 옮긴 것이 많다. 업계 소식일 뿐 소비자가 궁금해하지 않는 내용이면 점수를 낮게 준다.
- [커뮤니티]: 실사용자의 후기·질문·불만·비교가 담긴 날것의 목소리다. **인스타에서 가장 잘 먹히는 소재원**이다. "다들 이거 궁금해했는데 정리해봤다" 식으로 풀 수 있고, 실제 사용자 언어를 그대로 쓸 수 있어 공감과 저장을 동시에 잡는다. 반복적으로 올라오는 질문이나 강한 감정(감탄, 실망, 배신감)이 담긴 글은 높게 평가한다.
- [인플루언서]: 이 분야에서 지금 무엇이 화제인지, 어떤 앵글이 반응을 얻는지 보여주는 신호다. 이미 검증된 주제 프레임이라 활용 가치가 높다.
- [트렌드]: 지금 사람들이 실제로 검색하는 키워드다. 우리 카테고리와 연결되면 시의성 점수를 크게 준다. 관련 없으면 과감히 낮게 준다.

점수 분포를 아끼지 말 것: 평범한 소재는 40 이하, 확실한 소재만 75 이상을 준다.
scoreReason은 위 기준에 근거해 1~2문장으로. contentAngle은 이 소재를 어떤 프레임(예: "초보가 가장 많이 하는 실수 5가지", "A vs B 비교", "가격대별 추천", "해외 사용자들이 실제로 하는 질문 정리")으로 풀지 구체적으로 제안한다. 커뮤니티 소재라면 그 목소리를 어떻게 콘텐츠의 출발점으로 쓸지 명시한다. hookIdea는 실제 첫 슬라이드에 쓸 수 있는 한 줄 카피를 ${s.language}로 쓴다.`;
}

const KIND_LABEL: Record<string, string> = {
  news: '뉴스',
  community: '커뮤니티(실사용자 목소리)',
  influencer: '인플루언서',
  trend: '검색 트렌드',
  blog: '블로그',
};

export function scoreUserPrompt(items: SourceItem[]): string {
  const list = items
    .map(
      (it) =>
        `- id: ${it.id}\n  종류: [${KIND_LABEL[it.kind] ?? it.kind}]\n  제목: ${it.title}\n  출처: ${it.source} (${it.publishedAt})\n  내용: ${it.snippet || '(요약 없음)'}`
    )
    .join('\n');
  return `다음 소재 목록을 평가하라. 모든 소재에 대해 결과를 반환할 것.\n\n${list}`;
}

// ---------- 2) 캐러셀 콘텐츠 생성 ----------

export const CAROUSEL_SCHEMA = {
  type: 'object',
  properties: {
    slides: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          role: { type: 'string', enum: ['hook', 'content', 'cta'] },
          kicker: { type: 'string' },
          headline: { type: 'string' },
          body: { type: 'string' },
          imagePrompt: { type: 'string' },
        },
        required: ['role', 'kicker', 'headline', 'body', 'imagePrompt'],
        additionalProperties: false,
      },
    },
    caption: { type: 'string' },
    hashtags: { type: 'array', items: { type: 'string' } },
    commentKeyword: { type: 'string' },
  },
  required: ['slides', 'caption', 'hashtags', 'commentKeyword'],
  additionalProperties: false,
} as const;

/** 댓글 키워드 → DM 리드 마그넷 CTA 규칙. 2026년 피드 알고리즘이 댓글·공유·저장을 도달 신호로 크게 치는 점을 이용한다. */
function ctaRules(s: AppSettings): string {
  if (s.ctaMode === 'comment') {
    const magnet = s.leadMagnet?.trim() || '이 게시물 내용을 바로 따라 할 수 있는 단계별 가이드';
    return `3. 마지막 슬라이드(role: cta): **댓글 키워드 → DM 자료 발송** 구조로 쓴다.
   - headline: "[주제] 가이드 필요하세요?" 처럼 독자가 받을 것을 묻는 한 줄
   - body: 첫 줄에 '댓글에 "키워드" 라고 남겨주세요' (키워드는 큰따옴표로), 이어서 DM으로 보낼 것을 ✓ 체크리스트 3줄로 (각 줄 10자 내외), 마지막 줄에 "바로 보내드릴게요"
   - DM으로 보낼 자료: ${magnet}
   - commentKeyword 필드에 그 키워드를 반환한다. 조건: 한 단어, 2~4글자, 주제를 바로 떠올리게 하는 명사(예: "유튜브", "가이드", "레시피"), 띄어쓰기·특수문자 없음
   - 저장 유도는 캡션에서만 짧게 한다`;
  }
  return `3. 마지막 슬라이드(role: cta): 저장/팔로우 유도.
   - "도움이 됐다면 저장" + 계정 팔로우 이유를 한 줄로
   - commentKeyword 필드는 빈 문자열로 반환한다`;
}

function captionCtaRules(s: AppSettings): string {
  if (s.ctaMode === 'comment') {
    return `- 마지막 두 줄: 💬 댓글에 "키워드" 남기면 [DM으로 보낼 자료]를 DM으로 보내드려요 / 📌 나중에 따라 하려면 저장. 키워드는 마지막 슬라이드의 commentKeyword와 반드시 같은 단어`;
  }
  return `- 마지막에 저장/댓글 유도 질문 한 줄`;
}

export function carouselSystemPrompt(s: AppSettings): string {
  return `당신은 팔로워 수십만의 "${s.category}" 정보 계정을 키워 본 인스타그램 카피라이터이자 콘텐츠 디렉터다. 소재 하나를 받아 조회수·저장·공유가 나오는 캐러셀 게시물 전체를 만든다.

계정: ${s.brandName || '(브랜드명 미지정)'}
톤: ${s.brandTone}
타깃: ${s.targetAudience}
언어: ${s.language} (모든 산출물을 이 언어로 작성)

## 캐러셀 구조 (슬라이드 6~9장)
1. 첫 슬라이드(role: hook): 스크롤을 멈추는 단 한 줄. 원칙:
   - 15자 내외의 강한 카피. 숫자/반전/손실 회피/구체성 중 하나 이상 사용
   - "~하는 법" 같은 밋밋한 표현 대신 결과와 긴장감을 담을 것 (예: "이거 모르면 30만원 날립니다")
   - 가능하면 **결과 숫자 + 장벽 제거**를 한 화면에: headline에 결과("월 100만원 아끼는"), kicker에 독자의 첫 반론을 없애는 짧은 말("장비 없이", "하루 10분", "초보도")
   - body에는 다음 장으로 넘기게 만드는 서브 카피 한 줄 (무엇으로/어떻게 하는지 도구·방법 이름을 넣어 구체성 확보)
2. 본문 슬라이드(role: content, 4~7장): 한 슬라이드 = 한 메시지.
   - headline은 12자 내외 요점, body는 2~3문장의 알맹이 있는 설명
   - 뻔한 일반론 금지. 구체적 수치, 제품명, 실행 가능한 팁을 담을 것
   - kicker에 "01", "02" 같은 순번 또는 짧은 라벨
   - **단계형(튜토리얼) 구조**: 소재가 방법·도구·워크플로·레시피·세팅처럼 "따라 하는" 내용이면 아래 순서를 쓴다 (총 8~9장). 단계형은 저장률과 완주율이 가장 높은 구조다.
     ① 훅 → ② 문제/비교 슬라이드: "대부분 여기서 망합니다" 식으로 흔한 선택 ✗ vs 올바른 선택 ✓ 를 수치로 대비 (headline에 비교 요점, body에 "A: 수치 vs B: 수치" 한 줄 + 이유 한 줄)
     → ③~⑦ 1단계~N단계(3~5단계): kicker는 "1단계 — 핵심어" 형식, headline은 이 단계에서 하는 일, body는 "무엇을 넣으면 → 무엇이 나오는지"를 도구·화면 이름까지 구체적으로
     → ⑧ 결과 슬라이드: kicker "결과", headline "결과는 이겁니다" 류, body에 결과물이 어떤 모습인지(일정표, 숫자, 전후 비교)와 "내가 할 일은 ○○뿐" 한 줄
     → ⑨ CTA
   - 리스트·비교·뉴스형 소재는 기존 구조(훅 → 본문 4~6장 → CTA)를 유지한다
${ctaRules(s)}

${
    s.slideTheme === 'warm'
      ? `각 슬라이드의 imagePrompt는 슬라이드 중앙 브라우저 프레임 안에 들어갈 **플랫 일러스트 UI 목업**을 영어로 묘사한다. 사진이 아니라 "도구 화면"이다: 검색 결과 그리드, 채팅 화면, 설정 패널, 일정표, 비교표처럼 그 단계에서 실제로 보게 되는 화면을 단순한 도형으로. 스타일 고정: "flat vector illustration of a software UI mockup, dark charcoal panel with rounded cards, terracotta and mustard accents, no readable text, no photo, clean 2D, 16:9". 훅 슬라이드는 결과물(수익 대시보드, 완성 피드 등)을 보여주는 목업으로.`
      : `각 슬라이드의 imagePrompt는 해당 슬라이드 배경으로 어울리는 사진을 영어로 묘사한다
(photorealistic, 실제 촬영한 듯한 묘사, 텍스트 없는 이미지. 예: "close-up of camping gear on wooden table, warm morning light, shallow depth of field").`
  }

## 포스팅 본문(caption) 원칙
- 첫 줄이 전부다: 첫 문장은 훅 슬라이드와 다른 각도의 궁금증 유발 문장
- 본문은 캐러셀 내용을 반복하지 않고 보충 맥락, 개인적 관점, 부가 팁 제공
- 문단은 1~2문장 단위로 짧게 끊고 줄바꿈, 이모지는 절제해서 문단 앞에만
${captionCtaRules(s)}
- 해시태그는 caption에 넣지 말 것 (별도 필드)

## 해시태그 원칙 (15~20개)
- 대형(10만+ 게시물) 3~4개, 중형 6~8개, 소형/니치 5~8개 혼합
- 분야 관련성이 가장 중요. # 기호 없이 텍스트만 반환

## 소재가 커뮤니티/인플루언서 글일 때
실사용자의 목소리에서 출발한 소재라면, 그 점을 콘텐츠의 힘으로 쓴다.
- 훅에 실제 사람들의 질문·반응을 반영한다 (예: "해외에서 제일 많이 묻는 질문", "다들 이거 모르고 삽니다")
- 보도자료식 문장("~을 출시했다", "~라고 밝혔다") 대신 사람이 말하듯 쓴다
- 원문에 드러난 감정(감탄, 실망, 놀라움)과 구체적 표현을 살린다
- 다만 특정 개인의 글을 인용부호로 옮기거나 아이디를 노출하지 말 것. 여러 목소리를 묶어 "이런 반응이 많다" 수준으로 일반화한다

사실 관계: 소재에 없는 사실을 지어내지 말 것. 소재가 얇으면 일반적으로 검증된 지식으로 보강하되, 특정 수치나 고유 정보는 소재에 있는 것만 사용한다. 커뮤니티 글의 개인적 주장은 사실로 단정하지 말고 "그런 반응이 많다"는 틀로 다룬다.`;
}

export function carouselUserPrompt(item: SourceItem): string {
  return `다음 소재로 캐러셀 게시물을 만들어라.

소재 종류: [${KIND_LABEL[item.kind] ?? item.kind}]
제목: ${item.title}
출처: ${item.source} (${item.publishedAt})
내용: ${item.snippet || '(요약 없음)'}
링크: ${item.link}
${item.contentAngle ? `추천 앵글: ${item.contentAngle}` : ''}
${item.hookIdea ? `훅 아이디어(참고용, 더 좋은 안이 있으면 교체 가능): ${item.hookIdea}` : ''}`;
}

// ---------- 3) 수정·보완 (리파인) ----------

export function refineSystemPrompt(s: AppSettings): string {
  return (
    carouselSystemPrompt(s) +
    `\n\n## 수정 모드\n기존 게시물과 사용자의 수정 요청을 받는다. 요청된 부분만 반영하고, 언급되지 않은 부분은 기존 품질을 유지하거나 자연스럽게 개선한다. 전체 게시물(slides, caption, hashtags)을 완성된 형태로 다시 반환한다.`
  );
}

export function refineUserPrompt(post: Post, feedback: string): string {
  return `## 기존 게시물
${JSON.stringify(
    {
      slides: post.slides.map(({ bgImageUrl, ...rest }) => rest),
      caption: post.caption,
      hashtags: post.hashtags,
      commentKeyword: post.commentKeyword ?? '',
    },
    null,
    2
  )}

## 원 소재
제목: ${post.sourceItem.title}
요약: ${post.sourceItem.snippet}

## 사용자 수정 요청
${feedback}`;
}
