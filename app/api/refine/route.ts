import { NextResponse } from 'next/server';
import { getSettings, getPost, upsertPost } from '@/lib/store';
import { getClient, callStructured } from '@/lib/anthropic';
import {
  CAROUSEL_SCHEMA,
  refineSystemPrompt,
  refineUserPrompt,
} from '@/lib/prompts';
import type { CarouselDraft } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(req: Request) {
  try {
    const { postId, feedback } = (await req.json()) as {
      postId: string;
      feedback: string;
    };
    if (!feedback?.trim()) {
      return NextResponse.json({ error: '수정 요청 내용을 입력해 주세요.' }, { status: 400 });
    }
    const settings = await getSettings();
    const post = await getPost(postId);
    if (!post) {
      return NextResponse.json({ error: '게시물을 찾을 수 없습니다.' }, { status: 404 });
    }

    const client = getClient(settings);
    const draft = await callStructured<CarouselDraft>(client, {
      model: settings.model,
      system: refineSystemPrompt(settings),
      user: refineUserPrompt(post, feedback),
      schema: CAROUSEL_SCHEMA as unknown as Record<string, unknown>,
      maxTokens: 16000,
    });

    // 기존 배경 이미지는 슬라이드 순서 기준으로 최대한 보존
    const slides = draft.slides.map((s, i) => ({
      ...s,
      bgImageUrl: post.slides[i]?.bgImageUrl,
    }));

    const updated = {
      ...post,
      slides,
      caption: draft.caption,
      hashtags: draft.hashtags,
      status: 'draft' as const,
      slideImagePaths: [], // 내용이 바뀌었으므로 렌더링 다시 필요
      updatedAt: new Date().toISOString(),
      revisions: [...post.revisions, { at: new Date().toISOString(), feedback }],
    };
    await upsertPost(updated);
    return NextResponse.json({ post: updated });
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? String(e) }, { status: 500 });
  }
}
