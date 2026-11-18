// src/api.ts — 与本地 Node.js API 服务通信（只发送向量，不接收向量生成逻辑）
import type { Doc, SearchResult } from './types';

const BASE = ''; // 同源，Vite dev proxy 转发 /api 到本地服务

async function jfetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  const data = await r.json();
  if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
  return data as T;
}

export const api = {
  health: () => jfetch<{ ok: boolean; ready: boolean }>('/api/health'),

  addDocs: (kb: string, docs: Doc[]) =>
    jfetch<{ ok: boolean; count: number; writeMs: number }>(`/api/kb/${encodeURIComponent(kb)}/add`, {
      method: 'POST', body: JSON.stringify({ docs }),
    }),

  refresh: (kb: string) =>
    jfetch<{ ok: boolean; refreshMs: number }>(`/api/kb/${encodeURIComponent(kb)}/refresh`, {
      method: 'POST', body: '{}',
    }),

  search: (kb: string, p: { keyword: string; embedding: number[]; nResults: number; mode?: 'hybrid' | 'vector' }) =>
    jfetch<SearchResult>(`/api/kb/${encodeURIComponent(kb)}/search`, {
      method: 'POST', body: JSON.stringify(p),
    }),

  count: (kb: string) =>
    jfetch<{ ok: boolean; count: number; ids: string[] }>(`/api/kb/${encodeURIComponent(kb)}/count`),

  clear: (kb: string) =>
    jfetch<{ ok: boolean; deleted: number }>(`/api/kb/${encodeURIComponent(kb)}`, { method: 'DELETE' }),

  all: () => jfetch<{ ok: boolean; count: number; docs: Doc[] }>('/api/debug/all'),
};
