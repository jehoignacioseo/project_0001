import Link from 'next/link';
import { getPosts, getSettings, getItems } from '@/lib/store';

export const dynamic = 'force-dynamic';

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  draft: { text: '초안', cls: 'bg-gray-100 text-gray-700' },
  ready: { text: '발행 준비 완료', cls: 'bg-blue-100 text-blue-700' },
  published: { text: '발행됨', cls: 'bg-green-100 text-green-700' },
  failed: { text: '발행 실패', cls: 'bg-red-100 text-red-700' },
};

export default async function Dashboard() {
  const [posts, settings, items] = await Promise.all([
    getPosts(),
    getSettings(),
    getItems(),
  ]);
  const scored = items.filter((i) => i.viralScore !== undefined).length;
  const needsSetup = !settings.category && settings.keywords.length === 0;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-extrabold">대시보드</h1>
        <p className="mt-1 text-sm text-gray-600">
          소재 수집 → AI 선별 → 캐러셀 제작 → 수정 → 인스타그램 발행까지 한 곳에서.
        </p>
      </section>

      {needsSetup && (
        <div className="card border-accent/40 bg-orange-50">
          <p className="font-semibold">시작하기 전에 설정이 필요해요</p>
          <p className="mt-1 text-sm text-gray-600">
            운영할 카테고리(분야)와 키워드, Anthropic API 키를 먼저 입력해 주세요.
          </p>
          <Link href="/settings" className="btn-accent mt-3">
            설정하러 가기
          </Link>
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <p className="text-xs font-semibold text-gray-500">운영 카테고리</p>
          <p className="mt-1 truncate text-lg font-bold">
            {settings.category || '미설정'}
          </p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold text-gray-500">수집된 소재</p>
          <p className="mt-1 text-lg font-bold">
            {items.length}개 <span className="text-sm font-medium text-gray-500">(선별 완료 {scored})</span>
          </p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold text-gray-500">만든 게시물</p>
          <p className="mt-1 text-lg font-bold">
            {posts.length}개{' '}
            <span className="text-sm font-medium text-gray-500">
              (발행 {posts.filter((p) => p.status === 'published').length})
            </span>
          </p>
        </div>
      </section>

      <section className="card">
        <div className="flex items-center justify-between">
          <h2 className="font-bold">파이프라인</h2>
          <Link href="/collect" className="btn-primary">
            새 콘텐츠 만들기 시작 →
          </Link>
        </div>
        <ol className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
          <li className="rounded-lg bg-gray-50 p-4">
            <span className="font-bold">① 소재 수집·선별</span>
            <p className="mt-1 text-gray-600">
              카테고리 뉴스·트렌드를 자동 수집하고, AI가 조회수 가능성을 점수로 판정합니다.
            </p>
          </li>
          <li className="rounded-lg bg-gray-50 p-4">
            <span className="font-bold">② 캐러셀 제작·수정</span>
            <p className="mt-1 text-gray-600">
              훅부터 CTA까지 캐러셀 전체와 본문·해시태그를 생성하고, 원하는 만큼 수정합니다.
            </p>
          </li>
          <li className="rounded-lg bg-gray-50 p-4">
            <span className="font-bold">③ 자동 발행</span>
            <p className="mt-1 text-gray-600">
              확정하면 Instagram Graph API로 캐러셀을 자동 업로드합니다.
            </p>
          </li>
        </ol>
      </section>

      <section>
        <h2 className="mb-3 font-bold">게시물</h2>
        {posts.length === 0 ? (
          <p className="text-sm text-gray-500">
            아직 만든 게시물이 없습니다. ① 소재 수집·선별에서 시작하세요.
          </p>
        ) : (
          <ul className="grid gap-3">
            {posts.map((p) => {
              const s = STATUS_LABEL[p.status];
              return (
                <li key={p.id}>
                  <Link
                    href={`/posts/${p.id}`}
                    className="card flex items-center justify-between gap-4 hover:border-ink"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold">
                        {p.slides[0]?.headline || p.sourceItem.title}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-gray-500">
                        소재: {p.sourceItem.title} · 슬라이드 {p.slides.length}장 ·{' '}
                        {new Date(p.updatedAt).toLocaleString('ko-KR')}
                      </p>
                    </div>
                    <span className={`badge shrink-0 ${s.cls}`}>{s.text}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
