'use client';

import { useEffect, useState } from 'react';
import type { AppSettings, SlideThemeId, SourceKind } from '@/lib/types';

const SOURCE_OPTIONS: { id: SourceKind; label: string; desc: string }[] = [
  { id: 'news', label: '뉴스', desc: '구글 뉴스에서 카테고리 관련 최신 기사를 수집합니다.' },
  {
    id: 'community',
    label: '커뮤니티 (소비자 목소리)',
    desc: 'Reddit에서 실사용 후기·질문·불만을 수집합니다. 해외 반응을 얻기에 가장 좋습니다.',
  },
  {
    id: 'influencer',
    label: '인플루언서 (유튜브)',
    desc: '지정한 유튜브 채널의 최신 영상 주제를 수집합니다. 아래에 채널을 등록하세요.',
  },
  {
    id: 'trend',
    label: '검색 트렌드',
    desc: '지금 사람들이 실제로 검색하는 급상승 키워드를 수집합니다.',
  },
];

export default function SettingsPage() {
  const [s, setS] = useState<AppSettings | null>(null);
  // 쉼표/줄바꿈이 입력 중에 지워지지 않도록, 목록형 필드는 원문 문자열로 들고
  // 저장 시점에만 배열로 파싱한다.
  const [keywordsText, setKeywordsText] = useState('');
  const [feedsText, setFeedsText] = useState('');
  const [enKeywordsText, setEnKeywordsText] = useState('');
  const [subredditsText, setSubredditsText] = useState('');
  const [youtubeText, setYoutubeText] = useState('');
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((data: AppSettings) => {
        setS(data);
        setKeywordsText(data.keywords.join(', '));
        setFeedsText(data.customFeeds.join('\n'));
        setEnKeywordsText((data.englishKeywords ?? []).join(', '));
        setSubredditsText((data.subreddits ?? []).join(', '));
        setYoutubeText((data.youtubeChannels ?? []).join('\n'));
      });
  }, []);

  function set<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setS((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaved(false);
  }

  async function save() {
    if (!s) return;
    setBusy(true);
    const list = (text: string, sep: ',' | '\n') =>
      text.split(sep).map((v) => v.trim()).filter(Boolean);
    const payload: AppSettings = {
      ...s,
      keywords: list(keywordsText, ','),
      customFeeds: list(feedsText, '\n'),
      englishKeywords: list(enKeywordsText, ','),
      subreddits: list(subredditsText, ','),
      youtubeChannels: list(youtubeText, '\n'),
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
          <p className="mt-1 text-xs leading-relaxed text-gray-400">
            💡 &quot;K관광&quot;, &quot;K뷰티&quot; 같은 업계 용어를 넣으면 수출·투자·실적 같은 B2B
            기사가 주로 잡힙니다. 독자가 실제로 검색할 말(&quot;서울 가볼만한 곳&quot;, &quot;성수동
            카페&quot;, &quot;올리브영 추천&quot;)로 적어야 소비자용 소재가 모입니다.
          </p>
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
      </section>

      <section className="card space-y-4">
        <div>
          <h2 className="font-bold">소재 수집 소스</h2>
          <p className="mt-1 text-xs leading-relaxed text-gray-500">
            언론 기사만 모으면 콘텐츠가 보도자료처럼 딱딱해집니다. 실제 소비자·인플루언서의
            목소리를 함께 모으면 훨씬 공감되는 콘텐츠가 나옵니다.
          </p>
        </div>

        <div className="space-y-2">
          {SOURCE_OPTIONS.map((opt) => (
            <label key={opt.id} className="flex cursor-pointer items-start gap-3 rounded-lg bg-gray-50 p-3">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={s.enabledSources?.includes(opt.id) ?? false}
                onChange={(e) => {
                  const cur = new Set(s.enabledSources ?? []);
                  if (e.target.checked) cur.add(opt.id);
                  else cur.delete(opt.id);
                  set('enabledSources', Array.from(cur));
                }}
              />
              <span>
                <span className="text-sm font-semibold">{opt.label}</span>
                <span className="block text-xs text-gray-500">{opt.desc}</span>
              </span>
            </label>
          ))}
        </div>

        <div>
          <label className="label">영문 키워드 (쉼표 구분 — 해외 커뮤니티 검색에 사용)</label>
          <input
            className="input"
            value={enKeywordsText}
            placeholder="예: korean skincare, k-beauty, korean sunscreen"
            onChange={(e) => {
              setEnKeywordsText(e.target.value);
              setSaved(false);
            }}
          />
          <p className="mt-1 text-xs text-gray-400">
            해외 소비자 반응을 모으려면 꼭 채워주세요. 비워두면 한글 키워드로 검색합니다.
          </p>
        </div>

        <div>
          <label className="label">서브레딧 (쉼표 구분 — 커뮤니티 소스 사용 시)</label>
          <input
            className="input"
            value={subredditsText}
            placeholder="예: AsianBeauty, KoreanBeauty, SkincareAddiction"
            onChange={(e) => {
              setSubredditsText(e.target.value);
              setSaved(false);
            }}
          />
        </div>

        <div>
          <label className="label">유튜브 채널 (줄바꿈 구분 — 채널 ID 또는 채널 RSS 주소)</label>
          <textarea
            className="input"
            rows={2}
            value={youtubeText}
            placeholder="https://www.youtube.com/@채널이름"
            onChange={(e) => {
              setYoutubeText(e.target.value);
              setSaved(false);
            }}
          />
          <p className="mt-1 text-xs leading-relaxed text-gray-400">
            채널 주소를 그대로 붙여넣으면 됩니다 (예:{' '}
            <code className="rounded bg-gray-100 px-1">https://www.youtube.com/@채널이름</code>).
            채널 ID를 직접 찾을 필요 없습니다.
          </p>
        </div>

        <div>
          <label className="label">검색 트렌드 지역</label>
          <select
            className="input"
            value={s.trendsGeo || 'KR'}
            onChange={(e) => set('trendsGeo', e.target.value)}
          >
            <option value="KR">대한민국</option>
            <option value="US">미국</option>
            <option value="JP">일본</option>
            <option value="GB">영국</option>
            <option value="SG">싱가포르</option>
          </select>
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
