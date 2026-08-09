import Anthropic from '@anthropic-ai/sdk';
import type { AppSettings } from './types';

export function getClient(settings: AppSettings): Anthropic {
  const apiKey = settings.anthropicApiKey || process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      'Anthropic API 키가 설정되지 않았습니다. 설정 페이지에서 입력하거나 ANTHROPIC_API_KEY 환경변수를 지정하세요.'
    );
  }
  return new Anthropic({ apiKey });
}

/**
 * 구조화 출력(JSON Schema)으로 Claude를 호출하고 파싱된 JSON을 반환한다.
 * output_config.format 은 응답을 스키마에 맞는 유효한 JSON으로 강제한다.
 */
export async function callStructured<T>(
  client: Anthropic,
  opts: {
    model: string;
    system: string;
    user: string;
    schema: Record<string, unknown>;
    maxTokens?: number;
  }
): Promise<T> {
  const response = await client.messages.create({
    model: opts.model,
    max_tokens: opts.maxTokens ?? 16000,
    system: opts.system,
    messages: [{ role: 'user', content: opts.user }],
    output_config: {
      format: { type: 'json_schema', schema: opts.schema },
    },
  } as Anthropic.MessageCreateParamsNonStreaming);

  if (response.stop_reason === 'refusal') {
    throw new Error('모델이 요청을 거부했습니다. 소재 내용을 확인해 주세요.');
  }
  const text = response.content.find(
    (b): b is Anthropic.TextBlock => b.type === 'text'
  )?.text;
  if (!text) throw new Error('모델 응답이 비어 있습니다.');
  return JSON.parse(text) as T;
}
