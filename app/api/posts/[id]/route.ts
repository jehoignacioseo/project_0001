import { NextResponse } from 'next/server';
import { getPost, upsertPost, deletePost } from '@/lib/store';
import type { Post } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: Request,
  { params }: { params: { id: string } }
) {
  const post = await getPost(params.id);
  if (!post) return NextResponse.json({ error: 'not found' }, { status: 404 });
  return NextResponse.json({ post });
}

// 직접 편집(슬라이드 텍스트, 캡션, 해시태그, 테마 등) 저장
export async function PATCH(
  req: Request,
  { params }: { params: { id: string } }
) {
  const post = await getPost(params.id);
  if (!post) return NextResponse.json({ error: 'not found' }, { status: 404 });
  const body = (await req.json()) as Partial<Post>;

  const contentChanged =
    body.slides !== undefined || body.caption !== undefined || body.hashtags !== undefined;

  const updated: Post = {
    ...post,
    ...body,
    id: post.id,
    createdAt: post.createdAt,
    updatedAt: new Date().toISOString(),
    // 내용이 바뀌면 기존 렌더링 무효화
    slideImagePaths: contentChanged ? [] : body.slideImagePaths ?? post.slideImagePaths,
  };
  await upsertPost(updated);
  return NextResponse.json({ post: updated });
}

export async function DELETE(
  _req: Request,
  { params }: { params: { id: string } }
) {
  await deletePost(params.id);
  return NextResponse.json({ ok: true });
}
