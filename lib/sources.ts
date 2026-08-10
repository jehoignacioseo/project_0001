// 소재 수집 소스 정의.
// 언론 기사뿐 아니라 소비자·인플루언서의 실제 목소리까지 모으기 위해
// API 키 없이 접근 가능한 공개 피드들을 조합한다.

import type { SourceKind } from './types';

export interface FeedSpec {
  url: string;
  kind: SourceKind;
}

/** 언론 기사 — Google News 검색 RSS */
export function googleNewsFeed(query: string, lang: 'ko' | 'en' = 'ko'): FeedSpec {
  const params =
    lang === 'ko'
      ? 'hl=ko&gl=KR&ceid=KR:ko'
      : 'hl=en-US&gl=US&ceid=US:en';
  return {
    url: `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&${params}`,
    kind: 'news',
  };
}

/**
 * 소비자 목소리 — Reddit 검색 RSS.
 * 실사용 후기, 비교 질문, 불만, "이거 진짜 좋냐" 류의 날것의 반응이 모인다.
 * 해외 소비자 인사이트를 얻는 데 특히 유용하다.
 */
export function redditSearchFeed(query: string): FeedSpec {
  return {
    url: `https://www.reddit.com/search.rss?q=${encodeURIComponent(query)}&sort=top&t=month&limit=25`,
    kind: 'community',
  };
}

/** 소비자 목소리 — 특정 서브레딧의 인기 글 */
export function subredditFeed(name: string): FeedSpec {
  const clean = name.replace(/^\/?r\//i, '').trim();
  return {
    url: `https://www.reddit.com/r/${encodeURIComponent(clean)}/top/.rss?t=week`,
    kind: 'community',
  };
}

/**
 * 인플루언서 목소리 — 유튜브 채널 업로드 RSS.
 * 채널 ID(UC…), 완성된 피드 주소, 그리고 @핸들/채널 URL 을 모두 받는다.
 * 핸들은 채널 페이지에서 실제 채널 ID 를 찾아 변환한다 (사용자가 ID를 직접 찾을 필요 없음).
 */
export async function youtubeChannelFeed(idOrUrl: string): Promise<FeedSpec | null> {
  const trimmed = idOrUrl.trim();
  if (!trimmed) return null;

  // 이미 완성된 피드 주소
  if (/youtube\.com\/feeds\/videos\.xml/.test(trimmed)) {
    return { url: trimmed, kind: 'influencer' };
  }

  // 채널 ID 직접 입력 (UC로 시작하는 24자)
  const idMatch = trimmed.match(/(UC[\w-]{22})/);
  if (idMatch) {
    return {
      url: `https://www.youtube.com/feeds/videos.xml?channel_id=${idMatch[1]}`,
      kind: 'influencer',
    };
  }

  // @핸들 또는 채널 URL → 페이지에서 채널 ID 추출
  const handleMatch = trimmed.match(/@([\w.-]+)/);
  const pageUrl = /^https?:\/\//i.test(trimmed)
    ? trimmed
    : handleMatch
      ? `https://www.youtube.com/@${handleMatch[1]}`
      : null;
  if (!pageUrl) return null;

  const res = await fetch(pageUrl, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`유튜브 채널 페이지를 열 수 없습니다 (${res.status}): ${trimmed}`);
  const html = await res.text();
  const found = html.match(/"channelId":"(UC[\w-]{22})"/) ?? html.match(/(UC[\w-]{22})/);
  if (!found) throw new Error(`채널 ID를 찾지 못했습니다: ${trimmed}`);

  return {
    url: `https://www.youtube.com/feeds/videos.xml?channel_id=${found[1]}`,
    kind: 'influencer',
  };
}

/** 검색 트렌드 — 지금 사람들이 실제로 검색하는 키워드 */
export function googleTrendsFeed(geo = 'KR'): FeedSpec {
  return {
    url: `https://trends.google.com/trending/rss?geo=${encodeURIComponent(geo)}`,
    kind: 'trend',
  };
}

export const SOURCE_KIND_LABEL: Record<SourceKind, string> = {
  news: '뉴스',
  community: '커뮤니티',
  influencer: '인플루언서',
  trend: '트렌드',
  blog: '블로그',
};

export const SOURCE_KIND_STYLE: Record<SourceKind, string> = {
  news: 'bg-slate-100 text-slate-700',
  community: 'bg-orange-100 text-orange-700',
  influencer: 'bg-purple-100 text-purple-700',
  trend: 'bg-emerald-100 text-emerald-700',
  blog: 'bg-sky-100 text-sky-700',
};
