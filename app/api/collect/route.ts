import { NextResponse } from 'next/server';
import { getSettings, getItems, saveItems } from '@/lib/store';
import { collectItems } from '@/lib/rss';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

export async function POST() {
  try {
    const settings = await getSettings();
    const hasSearchTerm =
      settings.keywords.length > 0 ||
      settings.englishKeywords?.length > 0 ||
      Boolean(settings.category);
    const hasDirectFeed =
      settings.customFeeds.length > 0 ||
      settings.subreddits?.length > 0 ||
      settings.youtubeChannels?.length > 0;
    if (!hasSearchTerm && !hasDirectFeed) {
      return NextResponse.json(
        { error: '설정에서 카테고리 또는 키워드를 먼저 입력해 주세요.' },
        { status: 400 }
      );
    }

    const { items, errors } = await collectItems(settings);

    // 기존에 점수가 매겨진 소재는 유지 (제목 기준 매칭)
    const prev = await getItems();
    const prevByTitle = new Map(prev.map((p) => [p.title, p]));
    const merged = items.map((it) => {
      const old = prevByTitle.get(it.title);
      return old
        ? {
            ...it,
            id: old.id,
            viralScore: old.viralScore,
            scoreReason: old.scoreReason,
            contentAngle: old.contentAngle,
            hookIdea: old.hookIdea,
          }
        : it;
    });

    await saveItems(merged);
    return NextResponse.json({ items: merged, errors });
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? String(e) }, { status: 500 });
  }
}

export async function GET() {
  const items = await getItems();
  return NextResponse.json({ items });
}
