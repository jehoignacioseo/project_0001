'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { SourceItem, SourceKind } from '@/lib/types';
import { SOURCE_KIND_LABEL, SOURCE_KIND_STYLE } from '@/lib/sources';

type SortKey = 'score' | 'date';
type KindFilter = SourceKind | 'all';

export default function CollectPage() {
  const router = useRouter();
  const [items, setItems] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState<'collect' | 'score' | string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>('score');
  const [kindFilter, setKindFilter] = useState<KindFilter>('all');
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/collect')
      .then((r) => r.json())
      .then((d) => setItems(d.items ?? []));
  }, []);

  const sorted = useMemo(() => {
    const arr = items.filter((it) => kindFilter === 'all' || it.kind === kindFilter);
    if (sort === 'score') {
      arr.sort((a, b) => (b.viralScore ?? -1) - (a.viralScore ?? -1));
    } else {
      arr.sort((a, b) => (a.publishedAt < b.publishedAt ? 1 : -1));
    }
    return arr;
  }, [items, sort, kindFilter]);

  const kindCounts = useMemo(() => {
    const counts = new Map<SourceKind, number>();
    for (const it of items) counts.set(it.kind, (counts.get(it.kind) ?? 0) + 1);
    return counts;
  }, [items]);

  async function collect() {
    setLoading('collect');
    setError(null);
    try {
      const res = await fetch('/api/collect', { method: 'POST' });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setItems(d.items);
      if (d.errors?.length) {
        setError(`일부 피드 수집 실패: ${d.errors.length}건`);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  }

  async function score() {
    setLoading('score');
    setError(null);
    try {
      const res = await fetch('/api/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      setItems(d.items);
      setSort('score');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  }

  async function generate(itemId: string) {
    setLoading(itemId);
    setError(null);
    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ itemId }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error);
      router.push(`/posts/${d.post.id}`);
    } catch (e: any) {
      setError(e.message);
      setLoading(null);
    }
  }

  const unscored = items.filter((i) => i.viralScore === undefined).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold">① 소재 수집 · 선별</h1>
          <p className="mt-1 text-sm text-gray-600">
            키워드 기반으로 최신 뉴스·트렌드를 수집하고, AI가 인스타 조회수 가능성을 판정합니다.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={collect} disabled={loading !== null}>
            {loading === 'collect' ? '수집 중…' : '소재 수집 (새로고침)'}
          </button>
          <button className="btn-primary" onClick={score} disabled={loading !== null || unscored === 0}>
            {loading === 'score'
              ? 'AI 선별 중… (최대 1~2분)'
              : `AI 바이럴 점수 매기기${unscored ? ` (${Math.min(unscored, 30)}건)` : ''}`}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {items.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            className={`badge border ${kindFilter === 'all' ? 'border-ink bg-ink text-white' : 'border-gray-300 bg-white text-gray-600'}`}
            onClick={() => setKindFilter('all')}
          >
            전체 {items.length}
          </button>
          {(Array.from(kindCounts.entries()) as [SourceKind, number][]).map(([kind, n]) => (
            <button
              key={kind}
              className={`badge border ${
                kindFilter === kind
                  ? 'border-ink bg-ink text-white'
                  : `border-transparent ${SOURCE_KIND_STYLE[kind]}`
              }`}
              onClick={() => setKindFilter(kind)}
            >
              {SOURCE_KIND_LABEL[kind]} {n}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between text-sm">
        <p className="text-gray-500">
          {kindFilter === 'all' ? '총' : `${SOURCE_KIND_LABEL[kindFilter]}`} {sorted.length}개 소재 ·
          전체 선별 완료 {items.length - unscored}개
        </p>
        <div className="flex gap-1">
          <button
            className={`rounded-lg px-3 py-1 font-medium ${sort === 'score' ? 'bg-ink text-white' : 'bg-white border border-gray-300'}`}
            onClick={() => setSort('score')}
          >
            점수순
          </button>
          <button
            className={`rounded-lg px-3 py-1 font-medium ${sort === 'date' ? 'bg-ink text-white' : 'bg-white border border-gray-300'}`}
            onClick={() => setSort('date')}
          >
            최신순
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="card text-center text-sm text-gray-500">
          아직 수집된 소재가 없습니다. 위의 <b>소재 수집</b> 버튼을 눌러 시작하세요.
          <br />
          (설정에서 카테고리/키워드를 먼저 입력해야 합니다)
        </div>
      ) : (
        <ul className="grid gap-3">
          {sorted.map((it) => {
            const open = expanded === it.id;
            const score = it.viralScore;
            const scoreCls =
              score === undefined
                ? 'bg-gray-100 text-gray-500'
                : score >= 75
                  ? 'bg-green-100 text-green-700'
                  : score >= 50
                    ? 'bg-yellow-100 text-yellow-700'
                    : 'bg-gray-100 text-gray-600';
            return (
              <li key={it.id} className="card">
                <div className="flex items-start justify-between gap-4">
                  <button
                    className="min-w-0 text-left"
                    onClick={() => setExpanded(open ? null : it.id)}
                  >
                    <p className="font-semibold leading-snug">{it.title}</p>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-gray-500">
                      <span className={`badge ${SOURCE_KIND_STYLE[it.kind] ?? ''}`}>
                        {SOURCE_KIND_LABEL[it.kind] ?? it.kind}
                      </span>
                      {it.source} · {new Date(it.publishedAt).toLocaleDateString('ko-KR')}
                    </p>
                  </button>
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <span className={`badge ${scoreCls}`}>
                      {score === undefined ? '미평가' : `바이럴 ${score}점`}
                    </span>
                    <button
                      className="btn-accent"
                      onClick={() => generate(it.id)}
                      disabled={loading !== null}
                    >
                      {loading === it.id ? '제작 중… (1~2분)' : '콘텐츠 만들기 →'}
                    </button>
                  </div>
                </div>
                {open && (
                  <div className="mt-3 space-y-2 border-t border-gray-100 pt-3 text-sm">
                    {it.snippet && <p className="text-gray-600">{it.snippet}</p>}
                    {it.scoreReason && (
                      <p>
                        <b>판정 근거</b> — {it.scoreReason}
                      </p>
                    )}
                    {it.contentAngle && (
                      <p>
                        <b>추천 앵글</b> — {it.contentAngle}
                      </p>
                    )}
                    {it.hookIdea && (
                      <p>
                        <b>훅 아이디어</b> — “{it.hookIdea}”
                      </p>
                    )}
                    <a
                      href={it.link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block text-xs text-blue-600 underline"
                    >
                      원문 보기 ↗
                    </a>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
