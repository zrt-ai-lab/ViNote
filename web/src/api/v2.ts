export interface Asset {
  id: string;
  title: string;
  source_type: 'url' | 'upload' | 'local';
  source_uri: string | null;
  platform: string | null;
  platform_video_id: string | null;
  content_hash: string | null;
  duration_ms: number | null;
  created_at: string;
  deleted_at: string | null;
}

export interface Job { id: string; asset_id: string; kind: string; status: string; stage: string | null; error: string | null; attempt: number; }
export interface Segment { id: string; start_ms: number; end_ms: number; text: string; edited_text: string | null; speaker: string | null; language: string | null; confidence: number | null; }
export interface AssetDetail extends Asset { jobs: Job[]; artifacts: Record<string, unknown>[]; segments: Segment[]; highlights: Record<string, unknown>[]; flashcards: Record<string, unknown>[]; }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init?.headers } });
  if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(body?.detail || ('请求失败（' + response.status + '）')); }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const listAssets = () => request<Asset[]>('/api/v2/assets');
export const getAsset = (id: string) => request<AssetDetail>('/api/v2/assets/' + encodeURIComponent(id));
export const createAsset = (payload: Pick<Asset, 'title' | 'source_type' | 'source_uri'>) => request<Asset>('/api/v2/assets', { method: 'POST', body: JSON.stringify(payload) });
export const uploadAsset = (file: File) => { const data = new FormData(); data.append('file', file); return request<{ asset: Asset; job: Job }>('/api/v2/assets/upload', { method: 'POST', body: data }); };
