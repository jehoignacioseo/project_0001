// Instagram Graph API 발행 (비즈니스/크리에이터 계정 필요)
// 절차: 슬라이드별 media 컨테이너 생성 → 캐러셀 컨테이너 생성 → media_publish
// 이미지 URL은 인스타그램 서버가 접근 가능한 공개 URL이어야 한다.

const GRAPH = 'https://graph.facebook.com/v21.0';

interface IgConfig {
  accessToken: string;
  businessId: string;
}

async function ig(path: string, params: Record<string, string>, cfg: IgConfig) {
  const body = new URLSearchParams({ ...params, access_token: cfg.accessToken });
  const res = await fetch(`${GRAPH}/${path}`, { method: 'POST', body });
  const json = await res.json();
  if (!res.ok || json.error) {
    const msg = json?.error?.message ?? `HTTP ${res.status}`;
    throw new Error(`Instagram API 오류: ${msg}`);
  }
  return json as { id: string };
}

async function waitForContainer(containerId: string, cfg: IgConfig) {
  // 컨테이너 처리 완료 대기 (최대 60초)
  for (let i = 0; i < 20; i++) {
    const res = await fetch(
      `${GRAPH}/${containerId}?fields=status_code&access_token=${encodeURIComponent(cfg.accessToken)}`
    );
    const json = await res.json();
    if (json.status_code === 'FINISHED') return;
    if (json.status_code === 'ERROR') {
      throw new Error('Instagram 미디어 컨테이너 처리 실패 (이미지 URL 접근 가능 여부를 확인하세요)');
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error('Instagram 미디어 컨테이너 처리 시간 초과');
}

/**
 * 캐러셀(또는 단일 이미지) 게시. 성공 시 게시된 media id 반환.
 * imageUrls: 공개 접근 가능한 이미지 URL 목록 (1~10개)
 */
export async function publishCarousel(
  imageUrls: string[],
  caption: string,
  cfg: IgConfig
): Promise<string> {
  if (imageUrls.length === 0) throw new Error('발행할 이미지가 없습니다.');
  if (imageUrls.length > 10) throw new Error('캐러셀은 최대 10장까지 가능합니다.');

  if (imageUrls.length === 1) {
    const container = await ig(`${cfg.businessId}/media`, {
      image_url: imageUrls[0],
      caption,
    }, cfg);
    await waitForContainer(container.id, cfg);
    const published = await ig(`${cfg.businessId}/media_publish`, {
      creation_id: container.id,
    }, cfg);
    return published.id;
  }

  // 1) 자식 컨테이너들
  const children: string[] = [];
  for (const url of imageUrls) {
    const child = await ig(`${cfg.businessId}/media`, {
      image_url: url,
      is_carousel_item: 'true',
    }, cfg);
    children.push(child.id);
  }
  for (const id of children) await waitForContainer(id, cfg);

  // 2) 캐러셀 컨테이너
  const carousel = await ig(`${cfg.businessId}/media`, {
    media_type: 'CAROUSEL',
    children: children.join(','),
    caption,
  }, cfg);
  await waitForContainer(carousel.id, cfg);

  // 3) 발행
  const published = await ig(`${cfg.businessId}/media_publish`, {
    creation_id: carousel.id,
  }, cfg);
  return published.id;
}
