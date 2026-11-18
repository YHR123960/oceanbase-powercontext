/**
 * benchmark.ts — 在真实浏览器内运行的基准测试入口
 * 由 Playwright 打开 /benchmark.html 触发，结果写入 window.__BENCH_RESULT__
 */
import { embedBatch, embedOne, loadEmbedder, probeWebGPU } from './embedding';
import { api } from './api';
import { BENCH_KB, CORPUS, QUERIES, evaluate, median } from './dataset.mjs';
import type { BackendType, DType } from './types';

declare global {
  interface Window {
    __BENCH_RESULT__: unknown;
    __BENCH_STATUS__: string;
    __BENCH_START__: (config: string) => void;
  }
}

const statusEl = document.getElementById('status')!;
const outEl = document.getElementById('out')!;
const S = (s: string) => { statusEl.textContent = s; window.__BENCH_STATUS__ = s; };

type Config = { name: string; dtype: DType; forceBackend?: BackendType };
const CONFIGS: Config[] = [
  { name: 'A_fp32_wasm', dtype: 'fp32', forceBackend: 'wasm' },      // A: 非量化基线
  { name: 'B_int8_wasm', dtype: 'q8', forceBackend: 'wasm' },        // B: INT8 量化
  { name: 'C_int8_auto', dtype: 'q8', forceBackend: undefined },     // C: 自动(WebGPU优先/降级WASM)
];
const REPEATS = 5;

async function runConfig(cfg: Config) {
  S(`[${cfg.name}] 加载模型…`);
  // 加载模型（含首次下载）计时
  const t0 = performance.now();
  const { pipe, info } = await loadEmbedder({ dtype: cfg.dtype, forceBackend: cfg.forceBackend });
  const modelLoadMs = Math.round(performance.now() - t0);

  // 首次推理延迟（冷）
  const tFirst = performance.now();
  await embedOne(pipe, '首次推理预热样本');
  const firstInferMs = Math.round(performance.now() - tFirst);

  // 预热后推理延迟（重复5次取中位数）
  const warmMs: number[] = [];
  for (let i = 0; i < REPEATS; i++) {
    const t = performance.now();
    await embedOne(pipe, `预热推理样本 ${i}`);
    warmMs.push(Math.round(performance.now() - t));
  }

  // 文档 embedding 吞吐：对整个语料批量向量化，重复 REPEATS 次
  const texts = CORPUS.map(d => d.text);
  const docEmbedMs: number[] = [];
  let vectors: number[][] = [];
  for (let i = 0; i < REPEATS; i++) {
    const t = performance.now();
    vectors = await embedBatch(pipe, texts);
    docEmbedMs.push(Math.round(performance.now() - t));
  }
  const throughput = +(CORPUS.length / (median(docEmbedMs) / 1000)).toFixed(2);

  // 写入 seekdb（该配置独立 kb），测量写库与刷新
  const kb = `${BENCH_KB}_${cfg.name}`;
  await api.clear(kb).catch(() => {});
  const docs = CORPUS.map((d, i) => ({
    id: d.id, text: d.text, embedding: vectors[i],
    metadata: { source: `bench-${cfg.name}`, topic: d.topic },
  }));
  const writeMs: number[] = [];
  const refreshMs: number[] = [];
  for (let i = 0; i < REPEATS; i++) {
    // 每次重写需要先清空，保证写入量一致
    await api.clear(kb);
    const w = await api.addDocs(kb, docs);
    writeMs.push(w.writeMs);
    const r = await api.refresh(kb);
    refreshMs.push(r.refreshMs);
  }

  // 查询评测：每条查询测 queryEmbedMs / seekdbSearchMs / e2e，并算质量指标
  const queryEmbedMs: number[] = [];
  const searchMs: number[] = [];
  const e2eMs: number[] = [];
  let recalls1 = [], recalls5 = [], ndcg5 = [];
  for (const item of QUERIES) {
    const tq = performance.now();
    const qv = await embedOne(pipe, item.q);
    queryEmbedMs.push(Math.round(performance.now() - tq));
    const te = performance.now();
    const res = await api.search(kb, { keyword: item.q, embedding: qv, nResults: 10, mode: 'hybrid' });
    e2eMs.push(Math.round(performance.now() - te));
    searchMs.push(res.searchMs);
    const ids = res.hits.map(h => String(h.id).replace(`${kb}::`, ''));
    recalls1.push(evaluate(ids, item.rel, 1).recall);
    recalls5.push(evaluate(ids, item.rel, 5).recall);
    ndcg5.push(evaluate(ids, item.rel, 5).ndcg);
  }
  const avg = (a: number[]) => +(a.reduce((x, y) => x + y, 0) / a.length).toFixed(4);

  return {
    config: cfg.name,
    model: info,
    metrics: {
      modelLoadMs,
      firstInferMs,
      warmInferMsMedian: median(warmMs),
      docEmbedMsMedian: median(docEmbedMs),
      throughputDocsPerSec: throughput,
      dbWriteMsMedian: median(writeMs),
      indexRefreshMsMedian: median(refreshMs),
      queryEmbedMsMedian: median(queryEmbedMs),
      seekdbSearchMsMedian: median(searchMs),
      e2eQueryMsMedian: median(e2eMs),
      'recall@1': avg(recalls1),
      'recall@5': avg(recalls5),
      'ndcg@5': avg(ndcg5),
    },
    raw: { warmMs, docEmbedMs, writeMs, refreshMs, queryEmbedMs, searchMs, e2eMs, recalls1, recalls5, ndcg5 },
  };
}

window.__BENCH_START__ = async (configJson: string) => {
  const cfg: Config = JSON.parse(configJson);
  try {
    S(`[${cfg.name}] 开始`);
    const result = await runConfig(cfg);
    window.__BENCH_RESULT__ = result;
    S(`[${cfg.name}] 完成`);
    outEl.textContent = JSON.stringify(result, null, 2);
  } catch (e) {
    window.__BENCH_RESULT__ = { error: String(e), stack: (e as Error).stack };
    S(`[${cfg.name}] 失败: ${(e as Error).message}`);
    outEl.textContent = String((e as Error).stack || e);
  }
};

// 暴露 WebGPU 探测
(window as unknown as { __WEBGPU_PROBE__: () => Promise<unknown> }).__WEBGPU_PROBE__ = probeWebGPU;
S('就绪');
