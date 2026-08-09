// 런타임에 생성된 슬라이드 이미지를 서빙 (public/은 빌드 시점 파일만 서빙되므로 별도 라우트 사용)
import { NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

const UPLOADS_DIR = path.join(process.cwd(), 'data', 'uploads');

const MIME_BY_EXT: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.avif': 'image/avif',
};

export async function GET(
  _req: Request,
  { params }: { params: { path: string[] } }
) {
  const target = path.resolve(UPLOADS_DIR, ...params.path);
  // 경로 탈출 방지
  if (!target.startsWith(UPLOADS_DIR + path.sep)) {
    return new NextResponse('forbidden', { status: 403 });
  }
  try {
    const buf = await fs.readFile(target);
    return new NextResponse(new Uint8Array(buf), {
      headers: {
        'Content-Type': MIME_BY_EXT[path.extname(target).toLowerCase()] ?? 'image/png',
        'Cache-Control': 'public, max-age=3600',
      },
    });
  } catch {
    return new NextResponse('not found', { status: 404 });
  }
}
