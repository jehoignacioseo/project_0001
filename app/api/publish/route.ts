import { NextResponse } from 'next/server';
import { getSettings, getPost, upsertPost } from '@/lib/store';
import { publishCarousel } from '@/lib/instagram';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(req: Request) {
  const { postId } = (await req.json()) as { postId: string };
  const post = await getPost(postId);
  if (!post) return NextResponse.json({ error: '게시물을 찾을 수 없습니다.' }, { status: 404 });

  try {
    const settings = await getSettings();
    if (!settings.igAccessToken || !settings.igBusinessId) {
      throw new Error(
        '설정에서 Instagram 액세스 토큰과 비즈니스 계정 ID를 입력해 주세요.'
      );
    }
    if (!settings.publicBaseUrl) {
      throw new Error(
        '발행하려면 설정의 "공개 base URL"이 필요합니다. 인스타그램 서버가 슬라이드 이미지를 가져갈 수 있도록 이 앱이 공개 URL로 배포되어 있어야 합니다.'
      );
    }
    if (post.slideImagePaths.length === 0) {
      throw new Error('먼저 편집 화면에서 "슬라이드 이미지 생성"을 실행해 주세요.');
    }

    const base = settings.publicBaseUrl.replace(/\/$/, '');
    const urls = post.slideImagePaths.map((p) => `${base}${p}`);
    const caption =
      post.caption +
      (post.hashtags.length
        ? '\n\n' + post.hashtags.map((h) => `#${h.replace(/^#/, '')}`).join(' ')
        : '');

    const mediaId = await publishCarousel(urls, caption, {
      accessToken: settings.igAccessToken,
      businessId: settings.igBusinessId,
    });

    const updated = {
      ...post,
      status: 'published' as const,
      publishedMediaId: mediaId,
      publishError: undefined,
      updatedAt: new Date().toISOString(),
    };
    await upsertPost(updated);
    return NextResponse.json({ post: updated });
  } catch (e: any) {
    const updated = {
      ...post,
      status: 'failed' as const,
      publishError: e.message ?? String(e),
      updatedAt: new Date().toISOString(),
    };
    await upsertPost(updated);
    return NextResponse.json({ error: e.message ?? String(e), post: updated }, { status: 500 });
  }
}
