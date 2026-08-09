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

점수 분포를 아끼지 말 것: 평범한 소재는 40 이하, 확실한 소재만 75 이상을 준다.
scoreReason은 위 기준에 근거해 1~2문장으로. contentAngle은 이 소재를 어떤 프레임(예: "초보가 가장 많이 하는 실수 5가지", "A vs B 비교", "가격대별 추천")으로 풀지 구체적으로 제안한다. hookIdea는 실제 첫 슬라이드에 쓸 수 있는 한 줄 카피를 ${s.language}로 쓴다.`;
}

export function scoreUserPrompt(items: SourceItem[]): string {
  const list = items
    .map(
      (it) =>
        `- id: ${it.id}\n  제목: ${it.title}\n  출처: ${it.source} (${it.publishedAt})\n  요약: ${it.snippet || '(요약 없음)'}`
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
  },
  required: ['slides', 'caption', 'hashtags'],
  additionalProperties: false,
} as const;

export function carouselSystemPrompt(s: AppSettings): string {
  return `당신은 팔로워 수십만의 "${s.category}" 정보 계정을 키워 본 인스타그램 카피라이터이자 콘텐츠 디렉터다. 소재 하나를 받아 조회수·저장·공유가 나오는 캐러셀 게시물 전체를 만든다.

계정: ${s.brandName || '(브랜드명 미지정)'}
톤: ${s.brandTone}
타깃: ${s.targetAudience}
언어: ${s.language} (모든 산출물을 이 언어로 작성)

## 캐러셀 구조 (슬라이드 6~8장)
1. 첫 슬라이드(role: hook): 스크롤을 멈추는 단 한 줄. 원칙:
   - 15자 내외의 강한 카피. 숫자/반전/손실 회피/구체성 중 하나 이상 사용
   - "~하는 법" 같은 밋밋한 표현 대신 결과와 긴장감을 담을 것 (예: "이거 모르면 30만원 날립니다")
   - body에는 다음 장으로 넘기게 만드는 서브 카피 한 줄
2. 본문 슬라이드(role: content, 4~6장): 한 슬라이드 = 한 메시지.
   - headline은 12자 내외 요점, body는 2~3문장의 알맹이 있는 설명
   - 뻔한 일반론 금지. 구체적 수치, 제품명, 실행 가능한 팁을 담을 것
   - kicker에 "01", "02" 같은 순번 또는 짧은 라벨
3. 마지막 슬라이드(role: cta): 저장/팔로우 유도.
   - "도움이 됐다면 저장" + 계정 팔로우 이유를 한 줄로

각 슬라이드의 imagePrompt는 해당 슬라이드 배경으로 어울리는 사진을 영어로 묘사한다
(photorealistic, 실제 촬영한 듯한 묘사, 텍스트 없는 이미지. 예: "close-up of camping gear on wooden table, warm morning light, shallow depth of field").

## 포스팅 본문(caption) 원칙
- 첫 줄이 전부다: 첫 문장은 훅 슬라이드와 다른 각도의 궁금증 유발 문장
- 본문은 캐러셀 내용을 반복하지 않고 보충 맥락, 개인적 관점, 부가 팁 제공
- 문단은 1~2문장 단위로 짧게 끊고 줄바꿈, 이모지는 절제해서 문단 앞에만
- 마지막에 저장/댓글 유도 질문 한 줄
- 해시태그는 caption에 넣지 말 것 (별도 필드)

## 해시태그 원칙 (15~20개)
- 대형(10만+ 게시물) 3~4개, 중형 6~8개, 소형/니치 5~8개 혼합
- 분야 관련성이 가장 중요. # 기호 없이 텍스트만 반환

사실 관계: 소재에 없는 사실을 지어내지 말 것. 소재가 얇으면 일반적으로 검증된 지식으로 보강하되, 특정 수치나 고유 정보는 소재에 있는 것만 사용한다.`;
}

export function carouselUserPrompt(item: SourceItem): string {
  return `다음 소재로 캐러셀 게시물을 만들어라.

제목: ${item.title}
출처: ${item.source} (${item.publishedAt})
요약: ${item.snippet || '(요약 없음)'}
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
    { slides: post.slides.map(({ bgImageUrl, ...rest }) => rest), caption: post.caption, hashtags: post.hashtags },
    null,
    2
  )}

## 원 소재
제목: ${post.sourceItem.title}
요약: ${post.sourceItem.snippet}

## 사용자 수정 요청
${feedback}`;
}
