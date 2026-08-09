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
  SOURCE_KIND_LABEL,
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * 피드 하나를 가져온다.
 * 뉴스·커뮤니티 사이트는 짧은 시간에 여러 요청이 몰리면 429/403 으로 막으므로
 * 실패 시 잠깐 쉬었다가 한 번 더 시도한다.
 */
async function fetchOnce(url: string): Promise<string> {
  const res = await fetch(url, {
    headers: {
      // 브라우저형 User-Agent 가 없으면 Reddit 등이 차단한다.
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36',
      Accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
      'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
    },
    signal: AbortSignal.timeout(20000),
  });
  if (!res.ok) {
    const reason =
      res.status === 429
        ? '요청이 너무 잦아 일시적으로 차단됨 (429)'
        : res.status === 403
          ? '접근이 차단됨 (403)'
          : `요청 실패 (${res.status})`;
    throw new Error(reason);
  }
  return res.text();
}

async function fetchFeed(spec: FeedSpec): Promise<SourceItem[]> {
  // Reddit 은 www 가 막히는 경우가 있어 구버전 호스트로도 시도한다.
  const candidates = [spec.url];
  if (spec.url.includes('www.reddit.com')) {
    candidates.push(spec.url.replace('www.reddit.com', 'old.reddit.com'));
  }

  let xml: string | undefined;
  let lastError: unknown;
  for (const url of candidates) {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        xml = await fetchOnce(url);
        break;
      } catch (e) {
        lastError = e;
        if (attempt === 0) await sleep(1500);
      }
    }
    if (xml) break;
  }
  if (!xml) throw lastError;
  const doc = parser.parse(xml);

  const items: SourceItem[] = [];
  const now = new Date().toISOString();

  // RSS 2.0 (Google News, Reddit search, Google Trends 등)
  const channel = doc?.rss?.channel;
  for (const it of toArray(channel?.item)) {
    const sourceName =
      typeof it.source === 'object' ? it.source?.['#text'] : it.source;

    // 구글 트렌드는 검색량과 관련 뉴스를 별도 필드로 준다.
    // 검색어 하나만으로는 무슨 맥락인지 알 수 없으므로 관련 뉴스를 본문에 합친다.
    const traffic = it['ht:approx_traffic'];
    const newsItems = toArray(it['ht:news_item']);
    const newsText = newsItems
      .map((n: any) =>
        [n?.['ht:news_item_title'], n?.['ht:news_item_snippet']]
          .filter(Boolean)
          .map(String)
          .join(' — ')
      )
      .filter(Boolean)
      .join(' / ');

    const snippet = stripHtml(
      [
        traffic ? `검색량 ${traffic}` : '',
        newsText,
        String(it.description ?? ''),
      ]
        .filter(Boolean)
        .join(' · ')
    ).slice(0, 600);

    items.push({
      id: newId('item'),
      title: stripHtml(String(it.title ?? '')),
      link: String(it.link ?? ''),
      source: stripHtml(String(sourceName ?? channel?.title ?? '')),
      kind: spec.kind,
      publishedAt: it.pubDate ? new Date(it.pubDate).toISOString() : now,
      snippet,
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

/**
 * 트렌드 소스는 카테고리와 무관한 전국 급상승 검색어를 모두 내려주므로
 * ("주유소", "이혼 소송" …) 우리 분야와 실제로 맞닿은 것만 남긴다.
 */
function buildRelevanceTerms(settings: AppSettings): string[] {
  const raw = [
    settings.category,
    ...settings.keywords,
    ...(settings.englishKeywords ?? []),
  ].filter(Boolean);

  const terms = new Set<string>();
  for (const phrase of raw) {
    const normalized = phrase.toLowerCase().trim();
    if (normalized.length >= 2) terms.add(normalized);
    // "K뷰티 신상품" 처럼 여러 단어면 개별 단어로도 매칭한다.
    for (const word of normalized.split(/[\s,/]+/)) {
      if (word.length >= 2) terms.add(word);
    }
  }
  return Array.from(terms);
}

function isRelevant(item: SourceItem, terms: string[]): boolean {
  if (terms.length === 0) return true;
  const haystack = `${item.title} ${item.snippet}`.toLowerCase();
  return terms.some((t) => haystack.includes(t));
}

/** 피드들을 병렬 수집하고 제목 기준으로 중복을 제거한다. */
export async function collectItems(
  settings: AppSettings
): Promise<{ items: SourceItem[]; errors: string[] }> {
  const feeds = buildFeeds(settings);
  const errors: string[] = [];
  const all: SourceItem[] = [];

  // 동시에 여러 요청을 보내면 뉴스·커뮤니티 사이트가 차단하므로
  // 소수씩 나눠 보내고 묶음 사이에 간격을 둔다.
  const BATCH = 2;
  for (let i = 0; i < feeds.length; i += BATCH) {
    const batch = feeds.slice(i, i + BATCH);
    const results = await Promise.allSettled(batch.map(fetchFeed));
    results.forEach((r, j) => {
      const spec = batch[j];
      if (r.status === 'fulfilled') all.push(...r.value);
      else {
        const host = (() => {
          try {
            return new URL(spec.url).hostname;
          } catch {
            return spec.url;
          }
        })();
        errors.push(
          `[${SOURCE_KIND_LABEL[spec.kind]}] ${host} — ${r.reason?.message ?? r.reason}`
        );
      }
    });
    if (i + BATCH < feeds.length) await sleep(800);
  }

  const terms = buildRelevanceTerms(settings);
  const seen = new Set<string>();
  const deduped = all.filter((it) => {
    if (!it.title || !it.link) return false;
    // 트렌드는 분야 무관 검색어가 섞여 오므로 관련 있는 것만 통과시킨다.
    if (it.kind === 'trend' && !isRelevant(it, terms)) return false;
    const key = it.title.toLowerCase().replace(/\s+/g, '').slice(0, 60);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  deduped.sort((a, b) => (a.publishedAt < b.publishedAt ? 1 : -1));

  // 한 종류가 목록을 독점하지 않도록 종류별 상한을 둔다.
  const LIMIT_BY_KIND: Record<string, number> = { trend: 10 };
  const perKind: Record<string, number> = {};
  const balanced = deduped.filter((it) => {
    perKind[it.kind] = (perKind[it.kind] ?? 0) + 1;
    return perKind[it.kind] <= (LIMIT_BY_KIND[it.kind] ?? 30);
  });

  return { items: balanced.slice(0, 80), errors };
}
