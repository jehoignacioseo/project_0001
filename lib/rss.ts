// 소재 수집: 여러 공개 피드(뉴스 / 커뮤니티 / 인플루언서 / 트렌드)를 병렬로 읽어온다.
import { XMLParser } from 'fast-xml-parser';
import { newId } from './store';
import type { AppSettings, SourceItem, SourceKind } from './types';
import {
  googleNewsFeed,
  redditSearchFeed,
  subredditFeed,
  youtubeChannelFeed,
  googleTrendsFeed,
  type FeedSpec,
} from './sources';

const parser = new XMLParser({ ignoreAttributes: false });

function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function toArray<T>(v: T | T[] | undefined): T[] {
  if (v === undefined) return [];
  return Array.isArray(v) ? v : [v];
}

async function fetchFeed(spec: FeedSpec): Promise<SourceItem[]> {
  const res = await fetch(spec.url, {
    headers: {
      // Reddit 등은 브라우저형 User-Agent 가 없으면 차단한다.
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
      Accept: 'application/rss+xml, application/xml, text/xml, */*',
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`요청 실패 (${res.status})`);
  const xml = await res.text();
  const doc = parser.parse(xml);

  const items: SourceItem[] = [];
  const now = new Date().toISOString();

  // RSS 2.0 (Google News, Reddit search, Google Trends 등)
  const channel = doc?.rss?.channel;
  for (const it of toArray(channel?.item)) {
    const sourceName =
      typeof it.source === 'object' ? it.source?.['#text'] : it.source;
    // 구글 트렌드는 검색량을 별도 필드로 준다.
    const traffic = it['ht:approx_traffic'];
    items.push({
      id: newId('item'),
      title: stripHtml(String(it.title ?? '')),
      link: String(it.link ?? ''),
      source: stripHtml(String(sourceName ?? channel?.title ?? '')),
      kind: spec.kind,
      publishedAt: it.pubDate ? new Date(it.pubDate).toISOString() : now,
      snippet: stripHtml(
        String(traffic ? `검색량 ${traffic} · ` : '') + String(it.description ?? '')
      ).slice(0, 600),
      collectedAt: now,
    });
  }

  // Atom (YouTube 채널, Reddit 서브레딧 등)
  const feed = doc?.feed;
  for (const e of toArray(feed?.entry)) {
    const link = toArray(e.link).find((l: any) => l?.['@_rel'] !== 'self');
    // 커뮤니티 글 작성자 아이디(/u/...)는 개인 식별자이므로 매체명으로 대체한다.
    const rawAuthor = String(e.author?.name ?? feed?.title?.['#text'] ?? feed?.title ?? '');
    const author = /^\/?u\//i.test(rawAuthor)
      ? stripHtml(String(feed?.title?.['#text'] ?? feed?.title ?? 'Reddit'))
      : rawAuthor;
    const body =
      e['media:group']?.['media:description'] ??
      e.summary?.['#text'] ??
      e.summary ??
      e.content?.['#text'] ??
      e.content ??
      '';
    items.push({
      id: newId('item'),
      title: stripHtml(String(e.title?.['#text'] ?? e.title ?? '')),
      link: String(link?.['@_href'] ?? ''),
      source: stripHtml(String(author ?? '')),
      kind: spec.kind,
      publishedAt:
        e.published || e.updated ? new Date(e.published ?? e.updated).toISOString() : now,
      snippet: stripHtml(String(body)).slice(0, 600),
      collectedAt: now,
    });
  }

  return items;
}

/** 설정에 따라 수집할 피드 목록을 구성한다. */
export function buildFeeds(settings: AppSettings): FeedSpec[] {
  const enabled = new Set<SourceKind>(
    settings.enabledSources?.length ? settings.enabledSources : ['news']
  );
  const koKeywords = settings.keywords.filter(Boolean);
  const searchTerms = koKeywords.length
    ? koKeywords
    : settings.category
      ? [settings.category]
      : [];
  const enTerms = settings.englishKeywords?.filter(Boolean) ?? [];

  const feeds: FeedSpec[] = [];

  if (enabled.has('news')) {
    feeds.push(...searchTerms.map((k) => googleNewsFeed(k, 'ko')));
    feeds.push(...enTerms.map((k) => googleNewsFeed(k, 'en')));
  }

  if (enabled.has('community')) {
    // 영문 키워드가 있으면 그걸로, 없으면 한글 키워드로 검색
    const terms = enTerms.length ? enTerms : searchTerms;
    feeds.push(...terms.map(redditSearchFeed));
    feeds.push(...(settings.subreddits ?? []).filter(Boolean).map(subredditFeed));
  }

  if (enabled.has('influencer')) {
    for (const ch of settings.youtubeChannels ?? []) {
      const spec = youtubeChannelFeed(ch);
      if (spec) feeds.push(spec);
    }
  }

  if (enabled.has('trend')) {
    feeds.push(googleTrendsFeed(settings.trendsGeo || 'KR'));
  }

  // 사용자 지정 RSS 는 항상 포함 (블로그로 분류)
  feeds.push(
    ...settings.customFeeds.filter(Boolean).map((url) => ({ url, kind: 'blog' as SourceKind }))
  );

  return feeds;
}

/** 피드들을 병렬 수집하고 제목 기준으로 중복을 제거한다. */
export async function collectItems(
  settings: AppSettings
): Promise<{ items: SourceItem[]; errors: string[] }> {
  const feeds = buildFeeds(settings);
  const errors: string[] = [];
  const results = await Promise.allSettled(feeds.map(fetchFeed));

  const all: SourceItem[] = [];
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') all.push(...r.value);
    else errors.push(`${feeds[i].url}: ${r.reason?.message ?? r.reason}`);
  });

  const seen = new Set<string>();
  const deduped = all.filter((it) => {
    if (!it.title || !it.link) return false;
    const key = it.title.toLowerCase().replace(/\s+/g, '').slice(0, 60);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  deduped.sort((a, b) => (a.publishedAt < b.publishedAt ? 1 : -1));

  // 한 종류가 목록을 독점하지 않도록 종류별 상한을 둔다.
  const perKind: Record<string, number> = {};
  const balanced = deduped.filter((it) => {
    perKind[it.kind] = (perKind[it.kind] ?? 0) + 1;
    return perKind[it.kind] <= 30;
  });

  return { items: balanced.slice(0, 80), errors };
}
