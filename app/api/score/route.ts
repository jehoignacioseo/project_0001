import { NextResponse } from 'next/server';
import { getSettings, getItems, saveItems } from '@/lib/store';
import { getClient, callStructured } from '@/lib/anthropic';
import { SCORE_SCHEMA, scoreSystemPrompt, scoreUserPrompt } from '@/lib/prompts';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

interface ScoreResult {
  results: {
    id: string;
    viralScore: number;
    scoreReason: string;
    contentAngle: string;
    hookIdea: string;
  }[];
}

export async function POST(req: Request) {
  try {
    const { itemIds } = (await req.json().catch(() => ({}))) as { itemIds?: string[] };
    const settings = await getSettings();
    const all = await getItems();

    // 지정된 소재만, 아니면 아직 점수 없는 소재 전부 (한 번에 최대 30개)
    const targets = (itemIds?.length
      ? all.filter((it) => itemIds.includes(it.id))
      : all.filter((it) => it.viralScore === undefined)
    ).slice(0, 30);

    if (targets.length === 0) {
      return NextResponse.json({ items: all, scored: 0 });
    }

    const client = getClient(settings);
    const result = await callStructured<ScoreResult>(client, {
      model: settings.model,
      system: scoreSystemPrompt(settings),
      user: scoreUserPrompt(targets),
      schema: SCORE_SCHEMA as unknown as Record<string, unknown>,
      maxTokens: 16000,
    });

    const byId = new Map(result.results.map((r) => [r.id, r]));
    const updated = all.map((it) => {
      const r = byId.get(it.id);
      if (!r) return it;
      return {
        ...it,
        viralScore: Math.max(0, Math.min(100, r.viralScore)),
        scoreReason: r.scoreReason,
        contentAngle: r.contentAngle,
        hookIdea: r.hookIdea,
      };
    });

    await saveItems(updated);
    return NextResponse.json({ items: updated, scored: result.results.length });
  } catch (e: any) {
    return NextResponse.json({ error: e.message ?? String(e) }, { status: 500 });
  }
}
