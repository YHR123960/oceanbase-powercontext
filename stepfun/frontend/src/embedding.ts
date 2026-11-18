/**
 * embedding.ts — 浏览器本地 embedding（Transformers.js）
 *
 * 硬性约束：
 *  - 所有文档/查询向量都在【浏览器本地】计算，绝不调用云端 embedding API。
 *  - env.allowRemoteModels = false：模型只能来自本地 public/models 目录。
 *  - 本模块只输出向量；写入数据库由 api.ts 发给本地 Node 服务完成。
 *
 * 后端选择：优先 WebGPU，不可用时自动降级 WASM。
 * 不能仅凭 navigator.gpu 存在就声称 WebGPU 成功——必须实际用 webgpu device
 * 完成一次推理且无异常，才会把 deviceVerified 置为 true。
 */
import { pipeline, env, type FeatureExtractionPipeline } from '@huggingface/transformers';
import type { BackendType, DType, ModelInfo } from './types';

// 禁用任何远程模型下载：这是"禁止云端推理/embedding"的第一道保障
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.localModelPath = '/models/';
env.useBrowserCache = true;

// ONNX Runtime Web 的 WASM 运行时文件也必须来自本地，否则 transformers.js
// 在模块初始化时会自动把 wasmPaths 指向 cdn.jsdelivr.net（见 transformers.js
// 内部 ONNX_ENV 初始化）。env.backends.onnx.wasm 与 ONNX_ENV.wasm 是同一对象引用，
// 因此必须就地修改其 wasmPaths 属性，而不是替换整个 wasm 对象。
// 文件由 scripts/copy-ort-assets.mjs 从 onnxruntime-web 复制到 public/ort/。
const ORT_BASE = '/ort/';
type OnnxBackend = { wasm?: { wasmPaths?: { mjs: string; wasm: string } } };
const onnxBackend = env.backends.onnx as OnnxBackend;
if (onnxBackend.wasm) {
  onnxBackend.wasm.wasmPaths = {
    mjs: `${ORT_BASE}ort-wasm-simd-threaded.asyncify.mjs`,
    wasm: `${ORT_BASE}ort-wasm-simd-threaded.asyncify.wasm`,
  };
}

const MODEL_ID = 'all-MiniLM-L6-v2';
const DIM = 384;

export interface EmbedPipelineOptions {
  dtype: DType;      // 'fp32' = 非量化基线, 'q8' = INT8 量化
  forceBackend?: BackendType; // 指定后端；不指定则自动(webgpu优先)
}

export interface LoadResult {
  pipe: FeatureExtractionPipeline;
  info: ModelInfo;
  downloadMs: number; // 模型首次加载(含下载)耗时
}

/** 浏览器是否具备可用的 WebGPU 适配器（真实 requestAdapter，非仅 navigator.gpu 存在） */
export async function probeWebGPU(): Promise<{ available: boolean; detail: string }> {
  const nav = navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown | null> } };
  if (!nav.gpu) return { available: false, detail: 'navigator.gpu 不存在' };
  try {
    const adapter = await nav.gpu.requestAdapter();
    if (!adapter) return { available: false, detail: 'navigator.gpu.requestAdapter() 返回 null' };
    return { available: true, detail: 'WebGPU adapter 可用（requestAdapter 成功）' };
  } catch (e) {
    return { available: false, detail: `requestAdapter 异常: ${(e as Error).message}` };
  }
}

/**
 * 加载 embedding pipeline。
 * 策略：若请求 webgpu，先用 webgpu device 加载并实际推理验证；失败则降级 wasm。
 */
export async function loadEmbedder(opts: EmbedPipelineOptions): Promise<LoadResult> {
  const t0 = performance.now();
  let device: BackendType = opts.forceBackend || 'webgpu';
  let deviceVerified = false;
  let detail = '';
  let pipe: FeatureExtractionPipeline | null = null;
  let lastErr: unknown = null;

  const dtype = opts.dtype;
  const tryDevices: BackendType[] = opts.forceBackend
    ? [opts.forceBackend]
    : ['webgpu', 'wasm'];

  for (const dev of tryDevices) {
    try {
      // device 与 dtype 显式配置，ONNX Runtime Web 按此选择执行提供器
      const p = await pipeline('feature-extraction', MODEL_ID, {
        dtype,
        device: dev,
      } as Parameters<typeof pipeline>[2]);
      // 实际推理验证：用 webgpu 声称成功前必须真的跑通一次推理
      const probe = await p('backend probe', { pooling: 'mean', normalize: true });
      if (probe.dims[probe.dims.length - 1] !== DIM) {
        throw new Error(`向量维度错误: ${probe.dims}`);
      }
      pipe = p;
      device = dev;
      deviceVerified = true;
      detail = dev === 'webgpu'
        ? 'WebGPU device 加载并实际推理成功（非仅检测 navigator.gpu）'
        : 'WASM device 加载并实际推理成功';
      break;
    } catch (e) {
      lastErr = e;
      detail = `${dev} 加载/推理失败: ${(e as Error).message}`;
      // webgpu 失败则继续尝试 wasm
      continue;
    }
  }

  if (!pipe) {
    throw new Error(`embedding pipeline 加载失败: ${detail}; ${(lastErr as Error)?.stack || ''}`);
  }

  const downloadMs = Math.round(performance.now() - t0);
  const info: ModelInfo = {
    name: MODEL_ID,
    baseModel: 'sentence-transformers/all-MiniLM-L6-v2',
    license: 'apache-2.0',
    dimension: DIM,
    dtype,
    quantization: dtype === 'q8' ? 'ONNX INT8 (dynamic quantization)' : 'FP32 (non-quantized baseline)',
    device,
    deviceVerified,
    detail,
  };
  return { pipe, info, downloadMs };
}

/** 对单条文本生成 embedding（本地推理） */
export async function embedOne(pipe: FeatureExtractionPipeline, text: string): Promise<number[]> {
  const out = await pipe(text, { pooling: 'mean', normalize: true });
  return Array.from(out.data as Float32Array | number[]);
}

/** 批量生成 embedding（本地推理，批处理提升吞吐） */
export async function embedBatch(pipe: FeatureExtractionPipeline, texts: string[]): Promise<number[][]> {
  const out = await pipe(texts, { pooling: 'mean', normalize: true });
  // 批量返回 shape [N, 384]
  const data = out.data as Float32Array | number[];
  const result: number[][] = [];
  for (let i = 0; i < texts.length; i++) {
    result.push(Array.from(data.slice(i * DIM, (i + 1) * DIM)));
  }
  return result;
}
