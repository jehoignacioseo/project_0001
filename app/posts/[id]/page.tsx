'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { toPng } from 'html-to-image';
import { SlideView } from '@/components/SlideView';
import type { Post, Slide, SlideThemeId, AppSettings } from '@/lib/types';

const THEME_OPTIONS: { id: SlideThemeId; label: string }[] = [
  { id: 'bold', label: '볼드 (다크+오렌지)' },
  { id: 'clean', label: '클린 (밝은 톤)' },
  { id: 'dark', label: '다크 (블루 포인트)' },
  { id: 'magazine', label: '매거진 (화이트)' },
];

export default function PostEditorPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [post, setPost] = useState<Post | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [feedback, setFeedback] = useState('');
  const [dirty, setDirty] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/api/posts/${id}`)
      .then((r) => r.json())
      .then((d) => setPost(d.post ?? null));
    fetch('/api/settings')
      .then((r) => r.json())
      .then(setSettings);
  }, [id]);

  const patch = useCallback(
    (updates: Partial<Post>) => {
      setPost((p) => (p ? { ...p, ...updates } : p));
      setDirty(true);
    },
    []
  );

  function updateSlide(i: number, updates: Partial<Slide>) {
    if (!post) return;
    const slides = post.slides.map((s, idx) => (idx === i ? { ...s, ...updates } : s));
    patch({ slides });
  }

  async function save() {
    if (!post) return;
    setBusy('save');
    setError(null);
    try {
      const res = await fetch(`/api/posts/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slides: post.slides,
          caption: post.caption,
          hashtags: post.hashtags,
          theme: post.theme,
        }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setPost(d.post);
      setDirty(false);
      setNotice('저장했습니다.');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function refine() {
    if (!post || !feedback.trim()) return;
    setBusy('refine');
    setError(null);
    try {
      if (dirty) await save();
      const res = await fetch('/api/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postId: id, feedback }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setPost(d.post);
      setFeedback('');
      setDirty(false);
      setNotice('AI 수정이 반영됐습니다.');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function renderSlides() {
    if (!post || !exportRef.current) return;
    setBusy('render');
    setError(null);
    try {
      if (dirty) await save();
      // 폰트 로딩 완료 대기
      await (document as any).fonts?.ready;
      const nodes = Array.from(
        exportRef.current.querySelectorAll<HTMLElement>('[data-slide]')
      );
      const images: string[] = [];
      for (const node of nodes) {
        const png = await toPng(node, {
          width: 1080,
          height: 1350,
          pixelRatio: 1,
          cacheBust: true,
        });
        images.push(png);
      }
      const res = await fetch('/api/slides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postId: id, images }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setPost(d.post);
      setNotice(`슬라이드 ${images.length}장을 이미지로 생성했습니다. 발행 준비 완료!`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    if (!post) return;
    if (!confirm('인스타그램에 지금 발행할까요? 발행 후에는 앱에서 되돌릴 수 없습니다.')) return;
    setBusy('publish');
    setError(null);
    try {
      const res = await fetch('/api/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ postId: id }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setPost(d.post);
      setNotice('🎉 인스타그램에 발행되었습니다!');
    } catch (e: any) {
      setError(e.message);
      // 실패 상태 반영
      fetch(`/api/posts/${id}`).then((r) => r.json()).then((d) => d.post && setPost(d.post));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!confirm('이 게시물을 삭제할까요?')) return;
    await fetch(`/api/posts/${id}`, { method: 'DELETE' });
    router.push('/');
  }

  if (!post) {
    return <p className="text-sm text-gray-500">불러오는 중…</p>;
  }

  const zipHashtags = post.hashtags.map((h) => `#${h.replace(/^#/, '')}`).join(' ');

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-extrabold leading-snug">② 캐러셀 편집 · ③ 발행</h1>
          <p className="mt-1 truncate text-sm text-gray-500">소재: {post.sourceItem.title}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={remove}>삭제</button>
          <button className="btn-ghost" onClick={save} disabled={busy !== null || !dirty}>
            {busy === 'save' ? '저장 중…' : dirty ? '변경사항 저장' : '저장됨'}
          </button>
          <button className="btn-primary" onClick={renderSlides} disabled={busy !== null}>
            {busy === 'render' ? '이미지 생성 중…' : '슬라이드 이미지 생성'}
          </button>
          <button
            className="btn-accent"
            onClick={publish}
            disabled={busy !== null || post.slideImagePaths.length === 0 || post.status === 'published'}
          >
            {busy === 'publish'
              ? '발행 중…'
              : post.status === 'published'
                ? '발행 완료'
                : '인스타그램에 발행 🚀'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      {notice && !error && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">{notice}</div>
      )}
      {post.status === 'published' && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          발행됨 · media id: {post.publishedMediaId}
        </div>
      )}

      {/* 미리보기 */}
      <section className="card overflow-x-auto">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-bold">미리보기</h2>
          <select
            className="input w-auto"
            value={post.theme}
            onChange={(e) => patch({ theme: e.target.value as SlideThemeId })}
          >
            {THEME_OPTIONS.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="flex gap-3 pb-2">
          {post.slides.map((s, i) => (
            <SlideView
              key={i}
              slide={s}
              theme={post.theme}
              index={i}
              total={post.slides.length}
              brandName={settings?.brandName}
              scale={0.22}
            />
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 슬라이드 편집 */}
        <section className="space-y-3">
          <h2 className="font-bold">슬라이드 편집</h2>
          {post.slides.map((s, i) => (
            <div key={i} className="card space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-gray-500">
                <span>
                  {i + 1}번 슬라이드 ·{' '}
                  {s.role === 'hook' ? '훅' : s.role === 'cta' ? 'CTA' : '본문'}
                </span>
              </div>
              <input
                className="input"
                value={s.kicker}
                placeholder="상단 라벨 (예: 01)"
                onChange={(e) => updateSlide(i, { kicker: e.target.value })}
              />
              <textarea
                className="input font-bold"
                rows={2}
                value={s.headline}
                placeholder="대형 카피"
                onChange={(e) => updateSlide(i, { headline: e.target.value })}
              />
              <textarea
                className="input"
                rows={3}
                value={s.body}
                placeholder="보조 텍스트"
                onChange={(e) => updateSlide(i, { body: e.target.value })}
              />
              <input
                className="input text-xs"
                value={s.bgImageUrl ?? ''}
                placeholder="배경 이미지 URL (선택 — 비우면 템플릿 배경)"
                onChange={(e) => updateSlide(i, { bgImageUrl: e.target.value || undefined })}
              />
              {s.imagePrompt && (
                <p className="text-xs text-gray-400">
                  💡 이미지 생성 프롬프트: {s.imagePrompt}
                </p>
              )}
            </div>
          ))}
        </section>

        {/* 본문/해시태그/AI 수정 */}
        <section className="space-y-4">
          <div className="card space-y-2">
            <h2 className="font-bold">포스팅 본문</h2>
            <textarea
              className="input"
              rows={10}
              value={post.caption}
              onChange={(e) => patch({ caption: e.target.value })}
            />
          </div>

          <div className="card space-y-2">
            <h2 className="font-bold">해시태그 ({post.hashtags.length}개)</h2>
            <textarea
              className="input"
              rows={3}
              value={zipHashtags}
              onChange={(e) =>
                patch({
                  hashtags: e.target.value
                    .split(/[\s,]+/)
                    .map((h) => h.replace(/^#/, ''))
                    .filter(Boolean),
                })
              }
            />
          </div>

          <div className="card space-y-2">
            <h2 className="font-bold">AI에게 수정 요청</h2>
            <p className="text-xs text-gray-500">
              예: “훅을 더 자극적으로”, “3번 슬라이드에 가격 비교 추가”, “본문을 더 캐주얼하게”
            </p>
            <textarea
              className="input"
              rows={3}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="어떻게 바꾸고 싶은지 자유롭게 적어주세요"
            />
            <button
              className="btn-primary w-full"
              onClick={refine}
              disabled={busy !== null || !feedback.trim()}
            >
              {busy === 'refine' ? 'AI 수정 중… (1~2분)' : 'AI 수정 실행'}
            </button>
            {post.revisions.length > 0 && (
              <details className="text-xs text-gray-500">
                <summary className="cursor-pointer">수정 이력 {post.revisions.length}건</summary>
                <ul className="mt-1 list-disc pl-4">
                  {post.revisions.map((r, i) => (
                    <li key={i}>
                      {new Date(r.at).toLocaleString('ko-KR')} — {r.feedback}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          {post.slideImagePaths.length > 0 && (
            <div className="card space-y-2">
              <h2 className="font-bold">생성된 슬라이드 이미지</h2>
              <div className="flex flex-wrap gap-2">
                {post.slideImagePaths.map((p) => (
                  <a key={p} href={p} target="_blank" rel="noreferrer">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={p} alt="" className="h-28 rounded border border-gray-200" />
                  </a>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* PNG 내보내기용 원본 크기 렌더링 (화면 밖) */}
      <div
        ref={exportRef}
        style={{ position: 'absolute', left: -99999, top: 0 }}
        aria-hidden
      >
        {post.slides.map((s, i) => (
          <div key={i} data-slide>
            <SlideView
              slide={s}
              theme={post.theme}
              index={i}
              total={post.slides.length}
              brandName={settings?.brandName}
              scale={1}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
