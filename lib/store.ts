// 단순 JSON 파일 기반 저장소 (1인 사용자 로컬/단일 인스턴스용)
import { promises as fs } from 'fs';
import path from 'path';
import type { AppSettings, Post, SourceItem } from './types';

const DATA_DIR = path.join(process.cwd(), 'data');

async function ensureDir() {
  await fs.mkdir(DATA_DIR, { recursive: true });
}

async function readJson<T>(file: string, fallback: T): Promise<T> {
  try {
    const raw = await fs.readFile(path.join(DATA_DIR, file), 'utf-8');
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

async function writeJson(file: string, data: unknown) {
  await ensureDir();
  const target = path.join(DATA_DIR, file);
  const tmp = target + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(data, null, 2), 'utf-8');
  await fs.rename(tmp, target);
}

export const DEFAULT_SETTINGS: AppSettings = {
  category: '',
  keywords: [],
  customFeeds: [],
  brandName: '',
  brandTone: '전문적이지만 친근한, 핵심만 간결하게 전달하는 톤',
  targetAudience: '해당 분야에 관심 많은 20~40대',
  slideTheme: 'bold',
  language: '한국어',
  model: 'claude-opus-5',
  anthropicApiKey: '',
  igAccessToken: '',
  igBusinessId: '',
  publicBaseUrl: '',
};

export async function getSettings(): Promise<AppSettings> {
  const saved = await readJson<Partial<AppSettings>>('settings.json', {});
  return { ...DEFAULT_SETTINGS, ...saved };
}

export async function saveSettings(settings: AppSettings) {
  await writeJson('settings.json', settings);
}

export async function getItems(): Promise<SourceItem[]> {
  return readJson<SourceItem[]>('items.json', []);
}

export async function saveItems(items: SourceItem[]) {
  await writeJson('items.json', items);
}

export async function getPosts(): Promise<Post[]> {
  return readJson<Post[]>('posts.json', []);
}

export async function savePosts(posts: Post[]) {
  await writeJson('posts.json', posts);
}

export async function getPost(id: string): Promise<Post | undefined> {
  const posts = await getPosts();
  return posts.find((p) => p.id === id);
}

export async function upsertPost(post: Post) {
  const posts = await getPosts();
  const idx = posts.findIndex((p) => p.id === post.id);
  if (idx >= 0) posts[idx] = post;
  else posts.unshift(post);
  await savePosts(posts);
}

export async function deletePost(id: string) {
  const posts = await getPosts();
  await savePosts(posts.filter((p) => p.id !== id));
}

export function newId(prefix = 'id'): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
