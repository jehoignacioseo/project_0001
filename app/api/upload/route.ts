// 슬라이드 배경 이미지 업로드/가져오기.
// - 파일 업로드: 사용자가 고른 이미지를 서버에 저장
// - URL 가져오기: 외부 이미지를 서버가 대신 내려받아 저장 (CORS 문제 원천 차단)
// 어느 쪽이든 결과는 같은 출처(/uploads/...)의 경로라 렌더링과 PNG 내보내기가 항상 동작한다.
import { NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';
import { newId } from '@/lib/store';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const ASSET_DIR = path.join(process.cwd(), 'data', 'uploads', 'assets');

const EXT_BY_MIME: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/gif': 'gif',
  'image/avif': 'avif',
};

async function save(bytes: Buffer, mime: string): Promise<string> {
  const ext = EXT_BY_MIME[mime];
  if (!ext) {
    throw new Error(
      `지원하지 않는 이미지 형식입니다 (${mime}). PNG, JPG, WEBP, GIF 파일을 사용해 주세요.`
    );
  }
  await fs.mkdir(ASSET_DIR, { recursive: true });
  const filename = `${newId('img')}.${ext}`;
  await fs.writeFile(path.join(ASSET_DIR, filename), bytes);
  return `/uploads/assets/${filename}`;
}

export async function POST(req: Request) {
  try {
    const contentType = req.headers.get('content-type') ?? '';

    // 1) 파일 업로드 (multipart/form-data)
    if (contentType.includes('multipart/form-data')) {
      const form = await req.formData();
      const file = form.get('file');
      if (!(file instanceof File)) {
        return NextResponse.json({ error: '파일이 없습니다.' }, { status: 400 });
      }
      if (file.size > 15 * 1024 * 1024) {
        return NextResponse.json(
          { error: '이미지가 너무 큽니다 (최대 15MB).' },
          { status: 400 }
        );
      }
      const url = await save(Buffer.from(await file.arrayBuffer()), file.type);
      return NextResponse.json({ url });
    }

    // 2) 외부 URL 가져오기
    const { url: sourceUrl } = (await req.json()) as { url?: string };
    if (!sourceUrl || !/^https?:\/\//i.test(sourceUrl)) {
      return NextResponse.json(
        { error: 'http(s):// 로 시작하는 이미지 주소를 입력해 주세요.' },
        { status: 400 }
      );
    }

    const res = await fetch(sourceUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; InstaContentStudio/1.0)' },
      redirect: 'follow',
      signal: AbortSignal.timeout(20000),
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `이미지를 가져오지 못했습니다 (HTTP ${res.status}).` },
        { status: 400 }
      );
    }

    const mime = (res.headers.get('content-type') ?? '').split(';')[0].trim();
    if (!mime.startsWith('image/')) {
      return NextResponse.json(
        {
          error:
            '이미지 파일 주소가 아닙니다. 공유 링크(share.google 등)나 웹페이지 주소는 사용할 수 없습니다. 이미지를 오른쪽 클릭 → "이미지 주소 복사"로 얻은 주소를 넣거나, 파일 업로드를 사용해 주세요.',
        },
        { status: 400 }
      );
    }

    const url = await save(Buffer.from(await res.arrayBuffer()), mime);
    return NextResponse.json({ url });
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? String(e) }, { status: 500 });
  }
}
