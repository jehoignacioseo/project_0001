'use client';

import { useEffect, useState } from 'react';
import type { AppSettings, SlideThemeId } from '@/lib/types';

export default function SettingsPage() {
  const [s, setS] = useState<AppSettings | null>(null);
  // 쉼표/줄바꿈이 입력 중에 지워지지 않도록, 목록형 필드는 원문 문자열로 들고
  // 저장 시점에만 배열로 파싱한다.
  const [keywordsText, setKeywordsText] = useState('');
  const [feedsText, setFeedsText] = useState('');
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((data: AppSettings) => {
        setS(data);
        setKeywordsText(data.keywords.join(', '));
        setFeedsText(data.customFeeds.join('\n'));
      });
  }, []);

  function set<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setS((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaved(false);
  }

  async function save() {
    if (!s) return;
    setBusy(true);
    const payload: AppSettings = {
      ...s,
      keywords: keywordsText.split(',').map((k) => k.trim()).filter(Boolean),
      customFeeds: feedsText.split('\n').map((u) => u.trim()).filter(Boolean),
    };
    setS(payload);
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setBusy(false);
    setSaved(true);
  }

  if (!s) return <p className="text-sm text-gray-500">불러오는 중…</p>;

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold">설정</h1>
        <button className="btn-primary" onClick={save} disabled={busy}>
          {busy ? '저장 중…' : saved ? '저장됨 ✓' : '저장'}
        </button>
      </div>

      <section className="card space-y-4">
        <h2 className="font-bold">콘텐츠 방향</h2>
        <div>
          <label className="label">카테고리 (분야) *</label>
          <input
            className="input"
            value={s.category}
            placeholder="예: 캠핑 용품, AI 트렌드, 홈카페, 재테크"
            onChange={(e) => set('category', e.target.value)}
          />
        </div>
        <div>
          <label className="label">수집 키워드 (쉼표 구분 — 비우면 카테고리로 검색)</label>
          <input
            className="input"
            value={keywordsText}
            placeholder="예: 캠핑 신제품, 캠핑 트렌드, 백패킹"
            onChange={(e) => {
              setKeywordsText(e.target.value);
              setSaved(false);
            }}
          />
        </div>
        <div>
          <label className="label">추가 RSS 피드 URL (줄바꿈 구분, 선택)</label>
          <textarea
            className="input"
            rows={3}
            value={feedsText}
            placeholder="https://example.com/feed.xml"
            onChange={(e) => {
              setFeedsText(e.target.value);
              setSaved(false);
            }}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">브랜드/계정 이름</label>
            <input
              className="input"
              value={s.brandName}
              placeholder="예: @camping_pick"
              onChange={(e) => set('brandName', e.target.value)}
            />
          </div>
          <div>
            <label className="label">기본 슬라이드 테마</label>
            <select
              className="input"
              value={s.slideTheme}
              onChange={(e) => set('slideTheme', e.target.value as SlideThemeId)}
            >
              <option value="bold">볼드 (다크+오렌지)</option>
              <option value="clean">클린 (밝은 톤)</option>
              <option value="dark">다크 (블루 포인트)</option>
              <option value="magazine">매거진 (화이트)</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label">톤앤매너</label>
          <input
            className="input"
            value={s.brandTone}
            onChange={(e) => set('brandTone', e.target.value)}
          />
        </div>
        <div>
          <label className="label">타깃 독자</label>
          <input
            className="input"
            value={s.targetAudience}
            onChange={(e) => set('targetAudience', e.target.value)}
          />
        </div>
      </section>

      <section className="card space-y-4">
        <h2 className="font-bold">AI (Claude)</h2>
        <div>
          <label className="label">Anthropic API 키</label>
          <input
            className="input"
            type="password"
            value={s.anthropicApiKey}
            placeholder="sk-ant-… (비우면 ANTHROPIC_API_KEY 환경변수 사용)"
            onChange={(e) => set('anthropicApiKey', e.target.value)}
          />
        </div>
        <div>
          <label className="label">모델</label>
          <select className="input" value={s.model} onChange={(e) => set('model', e.target.value)}>
            <option value="claude-opus-5">claude-opus-5 (권장 — 최고 품질)</option>
            <option value="claude-sonnet-5">claude-sonnet-5 (빠르고 저렴)</option>
          </select>
        </div>
      </section>

      <section className="card space-y-4">
        <h2 className="font-bold">인스타그램 발행 (선택)</h2>
        <p className="text-xs leading-relaxed text-gray-500">
          자동 발행에는 <b>Instagram 비즈니스/크리에이터 계정</b>과 Facebook 개발자 앱의{' '}
          <b>Graph API 액세스 토큰</b>(권한: instagram_basic, instagram_content_publish)이 필요합니다.
          또한 인스타그램 서버가 슬라이드 이미지를 가져갈 수 있도록 이 앱이 <b>공개 URL로 배포</b>되어
          있어야 합니다 (예: Vercel). 로컬에서는 제작·수정까지만 하고, 이미지를 다운로드해 수동
          업로드할 수도 있습니다.
        </p>
        <div>
          <label className="label">액세스 토큰</label>
          <input
            className="input"
            type="password"
            value={s.igAccessToken}
            onChange={(e) => set('igAccessToken', e.target.value)}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Instagram 비즈니스 계정 ID</label>
            <input
              className="input"
              value={s.igBusinessId}
              placeholder="1784…"
              onChange={(e) => set('igBusinessId', e.target.value)}
            />
          </div>
          <div>
            <label className="label">공개 base URL</label>
            <input
              className="input"
              value={s.publicBaseUrl}
              placeholder="https://my-app.vercel.app"
              onChange={(e) => set('publicBaseUrl', e.target.value)}
            />
          </div>
        </div>
      </section>

      <button className="btn-primary w-full" onClick={save} disabled={busy}>
        {busy ? '저장 중…' : saved ? '저장됨 ✓' : '설정 저장'}
      </button>
    </div>
  );
}
