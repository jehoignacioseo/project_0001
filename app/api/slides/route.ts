// 클라이언트에서 렌더링한 슬라이드 PNG를 저장하고 공개 경로를 반환
import { NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';
import { getPost, upsertPost } from '@/lib/store';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

export async function POST(req: Request) {
  try {
    const { postId, images } = (await req.json()) as {
      postId: string;
      images: string[]; // data URL (image/png)
    };
    const post = await getPost(postId);
    if (!post) return NextResponse.json({ error: 'not found' }, { status: 404 });

    // public/ 은 빌드 시점 파일만 서빙되므로, 런타임 업로드는 data/uploads 에 두고
    // app/uploads/[...path]/route.ts 가 서빙한다.
    const dir = path.join(process.cwd(), 'data', 'uploads', postId);
    await fs.rm(dir, { recursive: true, force: true });
    await fs.mkdir(dir, { recursive: true });

    const paths: string[] = [];
    for (let i = 0; i < images.length; i++) {
      const dataUrl = images[i];
      const base64 = dataUrl.replace(/^data:image\/png;base64,/, '');
      const filename = `slide-${String(i + 1).padStart(2, '0')}.png`;
      await fs.writeFile(path.join(dir, filename), Buffer.from(base64, 'base64'));
      paths.push(`/uploads/${postId}/${filename}`);
    }

    const updated = {
      ...post,
      slideImagePaths: paths,
      status: 'ready' as const,
      updatedAt: new Date().toISOString(),
    };
    await upsertPost(updated);
    return NextResponse.json({ post: updated });
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? String(e) }, { status: 500 });
  }
}
