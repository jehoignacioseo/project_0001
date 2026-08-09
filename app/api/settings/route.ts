import { NextResponse } from 'next/server';
import { getSettings, saveSettings, DEFAULT_SETTINGS } from '@/lib/store';
import type { AppSettings } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function GET() {
  const settings = await getSettings();
  return NextResponse.json(settings);
}

export async function POST(req: Request) {
  const body = (await req.json()) as Partial<AppSettings>;
  const current = await getSettings();
  const merged: AppSettings = { ...DEFAULT_SETTINGS, ...current, ...body };
  await saveSettings(merged);
  return NextResponse.json(merged);
}
