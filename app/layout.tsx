import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'Insta Content Studio',
  description: '카테고리 소재 수집 → AI 캐러셀 제작 → 인스타그램 자동 발행',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="min-h-screen">
        <header className="sticky top-0 z-40 border-b border-gray-200 bg-white/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
            <Link href="/" className="text-lg font-extrabold tracking-tight">
              Insta<span className="text-accent">Content</span>Studio
            </Link>
            <nav className="flex items-center gap-1 text-sm font-medium">
              <Link href="/" className="rounded-lg px-3 py-1.5 hover:bg-gray-100">
                대시보드
              </Link>
              <Link href="/collect" className="rounded-lg px-3 py-1.5 hover:bg-gray-100">
                ① 소재 수집·선별
              </Link>
              <Link href="/settings" className="rounded-lg px-3 py-1.5 hover:bg-gray-100">
                설정
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
