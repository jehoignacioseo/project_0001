// 소재 수집: Google News RSS(키 불필요) + 사용자 지정 RSS 피드
import { XMLParser } from 'fast-xml-parser';
import { newId } from './store';
import type { SourceItem } from './types';

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

async function fetchFeed(url: string): Promise<SourceItem[]> {
  const res = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; InstaContentStudio/1.0)' },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`RSS 요청 실패 (${res.status}): ${url}`);
  const xml = await res.text();
  const doc = parser.parse(xml);

  const items: SourceItem[] = [];
  const now = new Date().toISOString();

  // RSS 2.0
  const rssItems = toArray(doc?.rss?.channel?.item);
  for (const it of rssItems) {
    const sourceName =
      typeof it.source === 'object' ? it.source?.['#text'] : it.source;
    items.push({
      id: newId('item'),
      title: stripHtml(String(it.title ?? '')),
      link: String(it.link ?? ''),
      source: stripHtml(String(sourceName ?? doc?.rss?.channel?.title ?? '')),
      publishedAt: it.pubDate ? new Date(it.pubDate).toISOString() : now,
      snippet: stripHtml(String(it.description ?? '')).slice(0, 500),
      collectedAt: now,
    });
  }

  // Atom
  const atomEntries = toArray(doc?.feed?.entry);
  for (const e of atomEntries) {
    const link = toArray(e.link).find((l: any) => l?.['@_rel'] !== 'self');
    items.push({
      id: newId('item'),
      title: stripHtml(String(e.title?.['#text'] ?? e.title ?? '')),
      link: String(link?.['@_href'] ?? ''),
      source: stripHtml(String(doc?.feed?.title?.['#text'] ?? doc?.feed?.title ?? '')),
      publishedAt: e.published || e.updated ? new Date(e.published ?? e.updated).toISOString() : now,
      snippet: stripHtml(String(e.summary?.['#text'] ?? e.summary ?? e.content?.['#text'] ?? '')).slice(0, 500),
      collectedAt: now,
    });
  }

  return items;
}

export function googleNewsUrl(query: string): string {
  return `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=ko&gl=KR&ceid=KR:ko`;
}

/** 키워드 + 사용자 피드에서 소재를 수집하고 제목 기준으로 중복 제거 */
export async function collectItems(
  keywords: string[],
  customFeeds: string[]
): Promise<{ items: SourceItem[]; errors: string[] }> {
  const urls = [
    ...keywords.filter(Boolean).map(googleNewsUrl),
    ...customFeeds.filter(Boolean),
  ];
  const errors: string[] = [];
  const results = await Promise.allSettled(urls.map(fetchFeed));

  const all: SourceItem[] = [];
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') all.push(...r.value);
    else errors.push(`${urls[i]}: ${r.reason?.message ?? r.reason}`);
  });

  // 제목 정규화 기준 중복 제거 + 최신순 정렬
  const seen = new Set<string>();
  const deduped = all.filter((it) => {
    const key = it.title.toLowerCase().replace(/\s+/g, '').slice(0, 60);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  deduped.sort((a, b) => (a.publishedAt < b.publishedAt ? 1 : -1));

  return { items: deduped.slice(0, 60), errors };
}
