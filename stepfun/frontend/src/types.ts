// src/types.ts — 前后端共享的数据结构定义

export type BackendType = 'webgpu' | 'wasm';
export type DType = 'fp32' | 'q8';

export interface ModelInfo {
  name: string;
  baseModel: string;
  license: string;
  dimension: number;
  dtype: DType;
  quantization: string;
  device: BackendType;
  deviceVerified: boolean;
  detail: string;
}

export interface Doc {
  id: string;
  text: string;
  embedding?: number[];
  metadata: { source: string; [k: string]: string | number | boolean };
}

export interface SearchHit {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
  distance: number | null;
}

export interface SearchResult {
  ok: boolean;
  hits: SearchHit[];
  searchMs: number;
  engine: string;
}

export interface BenchmarkMetric {
  name: string;
  samples: number[];
  median: number;
}
