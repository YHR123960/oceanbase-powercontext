# TEST_REPORT.md — 测试汇总（命令 / 退出码 / 环境 / 代码版本）

> 所有测试均为本机真实运行，日志原始文件在 `evidence/` 与 `backend/evidence/`。
> 环境：Windows 11 (10.0.26200)、Node v22.22.2、npm 10.9.7、Chrome (Playwright 1.65.1 headless)、seekdb 1.4.0。
> 代码版本：官方基础分支 `2026-competition-ecosystem` HEAD `d647275c308e09b7b623f322a26f5c4e85734fb0`；本机作品见本提交 SHA。

| # | 测试项 | 命令 | 退出码 | 结果摘要 | 证据 |
|---|---|---|---|---|---|
| 1 | 环境与依赖 | `node --version; npm --version; git --version; git ls-remote ...` | 0 | Node/npm/git/浏览器就绪；官方分支存在 | `evidence/stage1/env.log` |
| 2 | seekdb 原生 CRUD | `node _probe_bg.cjs`（已归档） | 0 | open/SELECT/CREATE/INSERT 全通过 | `evidence/stage1/seekdb_native_probe.log` |
| 3 | seekdb SDK 混合检索 | `node _probe_sdk2.cjs`（已归档） | 0 | add/refresh/hybridSearch/where 过滤通过 | `evidence/stage1/seekdb_sdk_hybrid.log` |
| 4 | 模型核验 | curl hf-mirror + 体积测量 | 0 | Apache-2.0 / 384维 / 压缩比 3.935× | `evidence/stage1/model_info.log` |
| 5 | API 端到端冒烟 | `node backend/scripts/api-smoke.mjs` | 0 | 10/10 PASS（导入/增量/刷新/混合检索/隔离） | `evidence/stage2_api_smoke.log` |
| 6 | 真实浏览器测试 | `node tests/browser-embedding.spec.mjs` | 0 | 6/6 PASS（本地推理/无云端请求/后端显示） | `evidence/browser/browser-test.log`、`app-wasm.png` |
| 7 | 知识库隔离与会话 | `node tests/kb-isolation.test.mjs` | 0 | 11/11 PASS | `evidence/kb-isolation.log` |
| 8 | 三配置性能与质量 | `node tests/run-benchmark.mjs` | 0 | A/B/C 全部跑通，5 次中位数 | `benchmark/results.json`、`evidence/benchmark/*.json` |
| 9 | 干净环境复现检查 | `node scripts/verify-fresh.mjs` | 0 | 30/30 PASS | `evidence/verify-fresh.log` |
| 10 | 前端构建 | `npm run build` (frontend) | 0 | TS 无错误，Vite 构建成功 | 终端输出（见 PROGRESS.md） |

## 未通过/受限项（如实记录）

- **WebGPU 推理验证**：本机 headless Chrome `navigator.gpu.requestAdapter()` 返回 null（"No available adapters"）。真实 WebGPU 路径未能验证；强制 WebGPU 时应用正确降级到 WASM。环境限制，非代码缺陷，未伪造成功结果。
- **C 配置首轮失败**：transformers.js/ORT 在同一页面内 WebGPU 失败后无法再初始化 WASM（全局状态污染）。改为每配置独立 page 后解决；C 配置以强制 WASM 实测降级路径。
- **量化质量下降**：INT8 的 Recall@5 (0.6806) 低于 FP32 (0.7083)，如实记录，未声称提升。

## 日志标注说明

每个证据日志内含时间戳；命令与退出码见本表；环境见本页顶部；代码版本见提交 SHA。原始性能数据 `benchmark/results.json` 含完整 env 字段（浏览器/OS/Node/WebGPU 状态/时间戳）与每次重复的原始数组。
