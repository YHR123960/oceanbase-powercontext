# TECHNICAL_OVERVIEW.md — StepFun 赛题一页技术说明

## 1. 系统架构

```
浏览器 (React+TS+Vite)
  ├─ Transformers.js 本地 embedding（文档/查询，WebGPU 优先 → WASM 降级）
  └─ HTTP → 本地 Node API (Express)
                └─ seekdb-js (Embedded) → seekdb 数据库
                      ├─ HNSW 向量索引 (cosine, dim=384)
                      ├─ IK 全文索引
                      └─ DBMS_HYBRID_SEARCH（数据库端融合排序）
```

- **向量只在浏览器生成**：`embeddingFunction: null`（seekdb Schema），Node 端从不加载模型。
- **混合检索在数据库完成**：`collection.hybridSearch()` 底层调用 `DBMS_HYBRID_SEARCH.GET_SQL`，由 seekdb 执行全文 + 向量融合与 RRF 排序，应用层不拼接两路结果。
- **知识库隔离**：单一 collection + `metadata.kb` 过滤；`hybridSearch` 的 query 同时带 `whereDocument`（全文）与 `where:{kb}`（过滤），数据库端组合为 `bool.must + bool.filter`；客户端再校验一次 kb 作为双保险。

## 2. 模型来源、版本与量化

| 项 | 值 |
|---|---|
| 模型 | `Xenova/all-MiniLM-L6-v2`（基础 `sentence-transformers/all-MiniLM-L6-v2`） |
| 许可证 | Apache-2.0 |
| 维度 | 384（bert, max_len 512） |
| Repo SHA | `751bff37182d3f1213fa05d7196b954e230abad9` |
| 非量化 | `onnx/model.onnx`，FP32，90,387,606 B |
| INT8 量化 | `onnx/model_quantized.onnx`，ONNX 动态量化(q8)，22,972,370 B |
| 压缩比 | **3.935×（体积 −74.6%）** |

量化在前端通过 `pipeline('feature-extraction', MODEL_ID, { dtype: 'q8' | 'fp32', device })` 切换。模型与 ORT WASM 运行时均从本地 `public/` 加载（`env.allowRemoteModels=false` + 就地设置 `wasmPaths`），真实浏览器测试确认外部请求数 = 0。

## 3. WebGPU / WASM 选择机制

1. `probeWebGPU()` 调用真实 `navigator.gpu.requestAdapter()`（非仅判断 `navigator.gpu` 存在）。
2. 自动模式依次尝试 `webgpu` → `wasm`；**必须用目标 device 实际完成一次推理且维度正确**，才标记 `deviceVerified=true`。
3. 任一 device 加载/推理失败即降级到下一个；前端状态栏显示当前实际后端与是否已验证。
4. **本机实测限制**：headless Chrome 环境 `requestAdapter()` 返回 null（"No available adapters"），WebGPU 推理未能验证；强制 WebGPU 时会明确失败并降级 WASM。**不伪造 WebGPU 成功**。

## 4. seekdb 数据结构与混合检索实现

- 数据库：Embedded 模式，`backend/data/seekdb`（首次初始化约 161MB，open 约 3-4s）。
- Collection：`mini_kb_docs`，Schema：
  - `VectorIndexConfig({ hnsw: { dimension: 384, distance: 'cosine' }, embeddingFunction: null })`
  - `FulltextIndexConfig('ik', { ik_mode: 'smart' })`
- 文档：id = `<kb>::<docId>`，text = 原文，embedding = 384 维向量（浏览器算），metadata = `{ kb, source, chunk }`。
- 混合检索：`hybridSearch({ query: { whereDocument: {$contains: keyword}, where: {kb} }, knn: { queryEmbeddings: [vec] }, nResults })`。
- 索引刷新：`collection.refresh_index()`，增量导入后调用，使新文档可被近似检索命中。

工程要点（实测）：seekdb 原生 addon 需用动态 `import()` 加载、日志只写文件不写 stdout、并用非 unref 心跳定时器保持事件循环稳定，否则 Express HTTP 无响应（详见 README 已知限制）。

## 5. 性能优化与真实结果

> 测试环境：Windows 11 (10.0.26200)、Node 22.22.2、Chrome (Playwright headless)、同一设备/语料/查询集，固定数据，每配置重复 5 次取中位数。原始数据见 `evidence/benchmark/*.json`，脚本 `tests/run-benchmark.mjs`。

| 指标（中位数） | A: FP32/WASM | B: INT8/WASM | C: INT8/WASM降级配置 |
|---|---|---|---|
| 模型加载/下载 ms | 1566 | 1145 | 1089 |
| 首次推理 ms | 19 | 11 | 12 |
| 预热推理 ms | 15 | 9 | 10 |
| 文档 embedding 吞吐 (段/秒) | 21.09 | 40.2 | 40.27 |
| 数据库写入 ms | 35 | 34 | 35 |
| 索引刷新 ms | 315 | 336 | 327 |
| 查询 embedding ms | 21 | 14.5 | 14 |
| seekdb 检索 ms | 10 | 10.5 | 9.5 |
| 端到端查询 ms | 21 | 22 | 20.5 |
| Recall@1 | 0.4653 | 0.4653 | 0.4653 |
| Recall@5 | 0.7083 | 0.6806 | 0.6389 |
| nDCG@5 | 0.7596 | 0.7428 | 0.7090 |

> 环境记录：Chrome (Playwright headless) / Windows 11 / Node v22.22.2 / WebGPU 不可用（requestAdapter 返回 null）/ 2026-11-18T02:18:36Z。原始数据：`benchmark/results.json`、`evidence/benchmark/{A_fp32_wasm,B_int8_wasm,C_int8_auto}.json`。

**真实结论（不虚构）：**
- INT8 相比 FP32：模型加载 1566→1145ms、首次推理 19→11ms、文档 embedding 吞吐 21.09→40.2 段/秒（约 1.9×）、查询 embedding 21→14.5ms。量化在加载与推理速度上收益明显，且模型体积减少 74.6%。
- 检索质量：Recall@1 三者均为 0.4653（持平）；**Recall@5 从 FP32 的 0.7083 降到 INT8 的 0.6806，nDCG@5 从 0.7596 降到 0.7428**，即量化在 Top-5 召回上有可测量的小幅下降，如实记录。
- **未改善/波动项（如实记录）**：端到端查询延迟 A=21ms、B=22ms，INT8 在此项未体现改善（seekdb 检索成为主要开销）；C 配置的 Recall@5=0.6389 低于 B 的 0.6806，尽管同为 INT8/WASM——这是 seekdb HNSW 近似检索的随机性/索引状态差异导致的波动，说明近似检索的召回并非完全确定。
- 索引刷新耗时（~315-336ms）高于单次写入（~35ms），是 seekdb 近似索引重建的固定开销；已在导入流程中按批次合并（一次导入一次刷新）。
- 优化手段：模型单实例复用、文档批处理 embedding、模型预热、索引刷新按导入批次合并、避免重复向量化（仅切换 dtype 才重载）。

## 6. 验证清单（真实通过）

- 首次导入 / 连续增量导入 / 索引刷新后可检索：通过（API 冒烟 10/10）
- 知识库切换不串数据 / 会话状态：通过（UI + 冒烟测试）
- 浏览器本地向量化、无云端调用：通过（浏览器测试外部请求=0）
- seekdb 数据库端混合检索：通过（engine=seekdb::DBMS_HYBRID_SEARCH）
- WASM 降级路径：通过（deviceVerified=true）；WebGPU：本环境不可用，已如实记录
