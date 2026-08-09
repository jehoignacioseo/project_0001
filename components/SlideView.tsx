'use client';

// 1080x1350(4:5) 캐러셀 슬라이드 렌더러.
// scale prop으로 미리보기 축소, 내보내기 시에는 scale=1 로 렌더링해 PNG 캡처한다.

import type { Slide, SlideThemeId } from '@/lib/types';

export const SLIDE_W = 1080;
export const SLIDE_H = 1350;

interface ThemeSpec {
  bg: string;
  fg: string;
  sub: string;
  kicker: string;
  accentBar: string;
  fontWeight: number;
  overlay: string; // 배경 이미지 위 오버레이
}

const THEMES: Record<SlideThemeId, ThemeSpec> = {
  bold: {
    bg: 'linear-gradient(160deg, #16181d 0%, #23262e 100%)',
    fg: '#ffffff',
    sub: 'rgba(255,255,255,0.78)',
    kicker: '#ff5c39',
    accentBar: '#ff5c39',
    fontWeight: 800,
    overlay: 'linear-gradient(180deg, rgba(10,12,16,0.35) 0%, rgba(10,12,16,0.82) 78%)',
  },
  clean: {
    bg: '#f6f4ef',
    fg: '#181a1f',
    sub: 'rgba(24,26,31,0.72)',
    kicker: '#c2410c',
    accentBar: '#181a1f',
    fontWeight: 800,
    overlay: 'linear-gradient(180deg, rgba(246,244,239,0.25) 0%, rgba(246,244,239,0.92) 72%)',
  },
  dark: {
    bg: '#0b0d10',
    fg: '#f2f2f0',
    sub: 'rgba(242,242,240,0.7)',
    kicker: '#7dd3fc',
    accentBar: '#7dd3fc',
    fontWeight: 800,
    overlay: 'linear-gradient(180deg, rgba(5,6,8,0.4) 0%, rgba(5,6,8,0.88) 80%)',
  },
  magazine: {
    bg: '#ffffff',
    fg: '#101014',
    sub: 'rgba(16,16,20,0.7)',
    kicker: '#101014',
    accentBar: '#e11d48',
    fontWeight: 800,
    overlay: 'linear-gradient(180deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.94) 70%)',
  },
};

export function SlideView({
  slide,
  theme,
  index,
  total,
  brandName,
  scale = 1,
}: {
  slide: Slide;
  theme: SlideThemeId;
  index: number;
  total: number;
  brandName?: string;
  scale?: number;
}) {
  const t = THEMES[theme];
  const isHook = slide.role === 'hook';
  const isCta = slide.role === 'cta';
  const hasImage = Boolean(slide.bgImageUrl);

  return (
    <div
      style={{
        width: SLIDE_W * scale,
        height: SLIDE_H * scale,
        overflow: 'hidden',
        borderRadius: scale < 1 ? 12 : 0,
        flexShrink: 0,
      }}
    >
      <div
        style={{
          width: SLIDE_W,
          height: SLIDE_H,
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          position: 'relative',
          background: t.bg,
          fontFamily:
            "'Pretendard Variable', Pretendard, -apple-system, 'Noto Sans KR', sans-serif",
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-end',
        }}
      >
        {hasImage && (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={slide.bgImageUrl}
              alt=""
              crossOrigin="anonymous"
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
            <div style={{ position: 'absolute', inset: 0, background: t.overlay }} />
          </>
        )}

        {/* 상단 바: 브랜드명 + 페이지 */}
        <div
          style={{
            position: 'absolute',
            top: 56,
            left: 72,
            right: 72,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            color: hasImage ? '#fff' : t.sub,
            fontSize: 30,
            fontWeight: 600,
            letterSpacing: '0.02em',
          }}
        >
          <span>{brandName || ''}</span>
          <span>
            {index + 1} / {total}
          </span>
        </div>

        {/* 본문 영역 */}
        <div
          style={{
            position: 'relative',
            padding: '0 84px 120px',
            display: 'flex',
            flexDirection: 'column',
            gap: 36,
            ...(isHook
              ? { paddingBottom: 0, justifyContent: 'center', height: '100%', paddingTop: 120 }
              : {}),
          }}
        >
          {slide.kicker ? (
            <div
              style={{
                color: hasImage && theme !== 'clean' && theme !== 'magazine' ? '#fff' : t.kicker,
                fontSize: 40,
                fontWeight: 800,
                letterSpacing: '0.06em',
                display: 'flex',
                alignItems: 'center',
                gap: 20,
              }}
            >
              <span style={{ width: 64, height: 8, background: t.accentBar, display: 'inline-block' }} />
              {slide.kicker}
            </div>
          ) : null}

          <div
            style={{
              color: hasImage && (theme === 'clean' || theme === 'magazine') ? t.fg : hasImage ? '#fff' : t.fg,
              fontSize: isHook ? 96 : isCta ? 76 : 68,
              lineHeight: 1.22,
              fontWeight: t.fontWeight,
              letterSpacing: '-0.02em',
              whiteSpace: 'pre-wrap',
              wordBreak: 'keep-all',
            }}
          >
            {slide.headline}
          </div>

          {slide.body ? (
            <div
              style={{
                color: hasImage ? 'rgba(255,255,255,0.85)' : t.sub,
                fontSize: 42,
                lineHeight: 1.5,
                fontWeight: 500,
                whiteSpace: 'pre-wrap',
                wordBreak: 'keep-all',
                maxWidth: 880,
              }}
            >
              {slide.body}
            </div>
          ) : null}

          {isHook && (
            <div
              style={{
                marginTop: 40,
                color: hasImage ? 'rgba(255,255,255,0.85)' : t.sub,
                fontSize: 36,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 14,
              }}
            >
              옆으로 넘겨보세요
              <span style={{ fontSize: 40 }}>→</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
