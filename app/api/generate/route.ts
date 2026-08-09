import { NextResponse } from 'next/server';
import { getSettings, getItems, upsertPost, newId } from '@/lib/store';
import { getClient, callStructured } from '@/lib/anthropic';
import {
  CAROUSEL_SCHEMA,
  carouselSystemPrompt,
  carouselUserPrompt,
} from '@/lib/prompts';
import type { CarouselDraft, Post } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(req: Request) {
  try {
    const { itemId } = (await req.json()) as { itemId: string };
    const settings = await getSettings();
    const items = await getItems();
    const item = items.find((it) => it.id === itemId);
    if (!item) {
      return NextResponse.json({ error: '소재를 찾을 수 없습니다.' }, { status: 404 });
    }

    const client = getClient(settings);
    const draft = await callStructured<CarouselDraft>(client, {
      model: settings.model,
      system: carouselSystemPrompt(settings),
      user: carouselUserPrompt(item),
      schema: CAROUSEL_SCHEMA as unknown as Record<string, unknown>,
      maxTokens: 16000,
    });

    const now = new Date().toISOString();
    const post: Post = {
      id: newId('post'),
      createdAt: now,
      updatedAt: now,
      status: 'draft',
      sourceItem: item,
      slides: draft.slides,
      caption: draft.caption,
      hashtags: draft.hashtags,
      theme: settings.slideTheme,
      slideImagePaths: [],
      revisions: [],
    };
    await upsertPost(post);
    return NextResponse.json({ post });
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? String(e) }, { status: 500 });
  }
}
