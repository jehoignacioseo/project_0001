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
  warm: {
    // 웜 튜토리얼: 크림 배경 + 테라코타 포인트. 레이아웃은 WarmSlide 가 따로 담당하고, 이 값은 폴백용.
    bg: '#F4EEE3',
    fg: '#2B2320',
    sub: 'rgba(43,35,32,0.68)',
    kicker: '#C4673A',
    accentBar: '#C4673A',
    fontWeight: 900,
    overlay: 'linear-gradient(180deg, rgba(244,238,227,0.2) 0%, rgba(244,238,227,0.9) 70%)',
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
  if (theme === 'warm') {
    return (
      <WarmSlide slide={slide} index={index} total={total} brandName={brandName} scale={scale} />
    );
  }

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

// ---------------------------------------------------------------------------
// 웜 튜토리얼 테마.
// 트렌드 캐러셀(단계형 AI 튜토리얼 + 댓글 키워드 DM) 의 레이아웃 상수를 그대로 따른다:
// 상단 @핸들 → 라벨 pill → 센터 정렬 헤드라인 → 브라우저 프레임 목업 → 설명 2줄
// → 우하단 "밀어서 보기 →" pill → 최하단 진행 점. 사진 대신 크림 배경 + 플랫 일러스트가 전제.
// ---------------------------------------------------------------------------

const WARM = {
  bg: '#F4EEE3',
  ink: '#2B2320',
  sub: '#5E534B',
  muted: '#9A8E84',
  accent: '#C4673A',
  accentSoft: '#F1DCCB',
  button: '#D37A4A',
  card: '#FFFFFF',
  line: '#D9CFC3',
};

function WarmSlide({
  slide,
  index,
  total,
  brandName,
  scale,
}: {
  slide: Slide;
  index: number;
  total: number;
  brandName?: string;
  scale: number;
}) {
  const isHook = slide.role === 'hook';
  const isCta = slide.role === 'cta';
  const isLast = index === total - 1;
  const handle = brandName ? (brandName.startsWith('@') ? brandName : `@${brandName}`) : '';
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
          background: `radial-gradient(ellipse at 50% 38%, #FBF7F0 0%, ${WARM.bg} 60%)`,
          color: WARM.ink,
          fontFamily:
            "'Pretendard Variable', Pretendard, -apple-system, 'Noto Sans KR', sans-serif",
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          padding: '150px 84px 230px',
          boxSizing: 'border-box',
          // 목업 이미지가 있으면 위에서부터 쌓고, 없으면 세로 중앙에 모은다
          justifyContent: hasImage && !isHook && !isCta ? 'flex-start' : 'center',
          gap: 36,
        }}
      >
        {/* 장식 점 (레퍼의 구석 점·별) */}
        {[
          { top: 300, left: 70 },
          { top: 980, left: 120 },
          { top: 420, right: 90 },
          { top: 1040, right: 70 },
        ].map((p, i) => (
          <span
            key={i}
            style={{
              position: 'absolute',
              width: 14,
              height: 14,
              borderRadius: 4,
              background: WARM.accent,
              opacity: 0.35,
              ...p,
            }}
          />
        ))}

        {/* 상단 @핸들 */}
        {handle && (
          <div
            style={{
              position: 'absolute',
              top: 64,
              left: 0,
              right: 0,
              color: WARM.muted,
              fontSize: 32,
              fontWeight: 600,
              letterSpacing: '0.08em',
            }}
          >
            {handle}
          </div>
        )}

        {/* 라벨 pill */}
        {slide.kicker ? (
          <div
            style={{
              display: 'inline-block',
              background: WARM.accentSoft,
              color: WARM.accent,
              fontSize: 32,
              fontWeight: 700,
              padding: '12px 32px',
              borderRadius: 999,
              letterSpacing: '0.02em',
            }}
          >
            {slide.kicker}
          </div>
        ) : null}

        {/* 헤드라인 */}
        <div
          style={{
            fontSize: isHook ? (hasImage ? 92 : 104) : 86,
            lineHeight: 1.16,
            fontWeight: 900,
            letterSpacing: '-0.03em',
            whiteSpace: 'pre-wrap',
            wordBreak: 'keep-all',
            maxWidth: 940,
          }}
        >
          {slide.headline}
        </div>

        {/* 훅의 서브카피는 테라코타 한 줄 */}
        {isHook && slide.body ? (
          <div
            style={{
              color: WARM.accent,
              fontSize: 44,
              fontWeight: 700,
              lineHeight: 1.4,
              whiteSpace: 'pre-wrap',
              wordBreak: 'keep-all',
              maxWidth: 900,
            }}
          >
            {slide.body}
          </div>
        ) : null}

        {/* 브라우저 프레임 목업 (이미지가 있을 때) */}
        {hasImage && (
          <div
            style={{
              width: 920,
              background: WARM.card,
              borderRadius: 28,
              boxShadow: '0 24px 60px rgba(43,35,32,0.14)',
              overflow: 'hidden',
              border: `2px solid ${WARM.line}`,
              marginTop: 8,
            }}
          >
            <div
              style={{
                height: 54,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '0 24px',
                borderBottom: `2px solid ${WARM.line}`,
                background: '#FAF6F0',
              }}
            >
              {['#E5756A', '#E9B85A', '#7CC27A'].map((c) => (
                <span key={c} style={{ width: 18, height: 18, borderRadius: 999, background: c }} />
              ))}
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={slide.bgImageUrl}
              alt=""
              crossOrigin="anonymous"
              style={{ display: 'block', width: '100%', height: isHook ? 340 : 520, objectFit: 'cover' }}
            />
          </div>
        )}

        {/* 본문 (훅 제외) */}
        {!isHook && slide.body ? (
          <div
            style={{
              color: isCta ? WARM.ink : WARM.sub,
              fontSize: isCta ? 44 : 40,
              lineHeight: 1.55,
              fontWeight: isCta ? 700 : 500,
              whiteSpace: 'pre-wrap',
              wordBreak: 'keep-all',
              maxWidth: 900,
              textAlign: isCta ? 'left' : 'center',
            }}
          >
            {slide.body}
          </div>
        ) : null}

        {/* 마지막 컷: 계정 사인오프 */}
        {isLast && handle ? (
          <div
            style={{
              marginTop: 12,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 16,
              background: WARM.card,
              border: `2px solid ${WARM.line}`,
              borderRadius: 999,
              padding: '14px 36px',
              fontSize: 34,
              fontWeight: 800,
            }}
          >
            {handle}
          </div>
        ) : null}

        {/* 우하단 "밀어서 보기 →" (마지막 컷 제외) */}
        {!isLast && (
          <div
            style={{
              position: 'absolute',
              right: 72,
              bottom: 150,
              background: WARM.button,
              color: '#fff',
              fontSize: 34,
              fontWeight: 800,
              padding: '18px 40px',
              borderRadius: 999,
              boxShadow: '0 10px 24px rgba(211,122,74,0.35)',
            }}
          >
            밀어서 보기 →
          </div>
        )}

        {/* 최하단 진행 점 */}
        <div
          style={{
            position: 'absolute',
            left: 84,
            right: 84,
            bottom: 84,
            height: 4,
            background: WARM.line,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          {Array.from({ length: total }).map((_, i) => (
            <span
              key={i}
              style={{
                width: i === index ? 26 : 12,
                height: i === index ? 26 : 12,
                borderRadius: 999,
                background: i === index ? WARM.accent : i < index ? WARM.accent : WARM.line,
                opacity: i < index ? 0.5 : 1,
                border: `3px solid ${WARM.bg}`,
                boxSizing: 'content-box',
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
