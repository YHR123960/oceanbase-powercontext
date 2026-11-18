# SUBMISSION.md — 提交规范核对与材料清单

> 本文件记录对官方赛题要求、提交方式与目录规范的逐项核对结果，以及本项目最终提交材料清单。
> 所有结论均来自官方公开文档与本机 git 实测，不推测、不虚构。

## 1. 官方依据（原文链接）

| 文档 | 地址 |
|---|---|
| 阶跃星辰赛题（本赛道） | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/kw9wfx4bu9pyvat9 |
| GitHub 在大赛中的使用说明 | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts |
| 比赛仓库地址 | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/brxxufkegusa86hl |
| 官方代码仓库 | https://github.com/oceanbase/powercontext |
| 官方基础分支 | `2026-competition-ecosystem`，HEAD `d647275c308e09b7b623f322a26f5c4e85734fb0` |

赛题原文关键要求（逐字引用）：

> 注意：为方便判题，请基于 https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem ，在测评平台提交时的分支/commit hash 基于此分支进行开发，相关项目资产放入对应 stepfun 目录中。在完成私有 repo 导入后，你已经获得一个同名的分支。

> 提交产物：可运行的 Web 应用、完整源码和一页技术说明

《GitHub 在大赛中的使用说明》关键要求：

> 一定要使用私有仓库进行测试。
> 首先你要有一个自己的 GitHub 账号……在网站右上角点击 "Import Repository"……填写导入表单……点击 "Begin import" 按钮，开始导入仓库……
> 生成token……在参赛信息里面填写好user:token的地址……仓库确认之后，开始提交测试。

《比赛仓库地址》中阶跃星辰一行：仓库 `oceanbase/powercontext`，分支 `2026-competition-ecosystem`，文件夹 `stepfun`。

## 2. 提交方式结论

| 核对项 | 结论 |
|---|---|
| 是否需要向官方仓库创建 GitHub Pull Request | **否**。官方说明要求导入自己的**私有仓库**，生成 token 后在**测评平台提交分支/commit hash**；未要求向 `oceanbase/powercontext` 提 PR。本交付严格遵守：无 remote、无 push、无 PR。 |
| 提交目标形态 | 私有仓库导入官方仓库 → 在 `2026-competition-ecosystem` 基础上开发 → 提交分支名 / commit hash。 |
| 资产放置位置 | 官方分支 `stepfun/` 目录（本项目顶层目录即与该目录一一对应）。 |
| 是否需要演示视频 | **未要求**。官方「四、提交材料」仅列 4.1 可运行 Web 应用、4.2 完整源码、4.3 一页技术说明。 |
| 是否需要截图 | **未作为硬性附件要求**。本项目仍附真实运行截图 `evidence/browser/app-wasm.png` 作为佐证。 |
| 是否需要性能报告 | 一页技术说明中**必须**包含关键性能对比结果（3.2 与 4.3）；本项目另有原始日志 `benchmark/results.json`、`evidence/benchmark/*.json` 作为可核验附件。 |

## 3. Git 基线核验（关键）

本地仓库已把作品提交接到官方基础提交之上，满足「commit hash 基于此分支进行开发」：

```
d647275  chore: initialize 2026 competition ecosystem directories   ← 官方 2026-competition-ecosystem HEAD
9f9d38c  feat(stepfun): complete mini knowledge base ...            ← 作品主提交
7a36999  docs(stepfun): record commit history reference ...         ← 文档 SHA 回填
05dd53d  docs(stepfun): add official submission checklist ...       ← 提交规范核对与证据整理
```

上述为稳定的作品里程碑提交；最新提交（含本文件后续修订）以 `git rev-parse HEAD` 为准。

核验命令与期望结果：

```bash
cd D:/OceanBase_WorkBuddy/StepFun_2026
git merge-base --is-ancestor d647275c308e09b7b623f322a26f5c4e85734fb0 HEAD && echo BASE_OK
git log --oneline -4
git remote -v        # 期望：无输出
```

官方占位文件 `dify/`、`gaode/`、`minimax/`、`qoder/` 均原样保留（含 `.gitkeep`），**未修改 Codex / MiniMax 或其他赛道资产**；`stepfun/.gitkeep` 已被真实作品内容替代。

## 4. 官方必做要求逐项对照

| 官方条目 | 本项目实现 | 证据 | 状态 |
|---|---|---|---|
| 2.1 导入文本文档 → 本地向量化 → 写入 seekdb → 混合检索 → 排序结果与原文 | React UI 导入/进度/结果/原文来源；`embedding.ts` 本地编码；`db.js` 写入；`hybridSearch()` 检索 | `frontend/src/App.tsx`、`evidence/browser/browser-test.log`、`evidence/browser/app-wasm.png` | 通过 |
| 2.2-1 浏览器本地执行 embedding（文档+查询） | Transformers.js 4.3.2，模型与 ORT WASM 均本地加载，`env.allowRemoteModels=false` | `frontend/src/embedding.ts`、`evidence/browser/browser-test.log`（`EXTERNAL_REQUEST_COUNT 0`） | 通过 |
| 2.2-2 开源模型，注明来源与版本 | `Xenova/all-MiniLM-L6-v2`，Apache-2.0，384 维，Repo SHA `751bff37…` | `TECHNICAL_OVERVIEW.md` §2、`evidence/stage1/model_info.log` | 通过 |
| 2.2-3 INT8/FP16 量化，体积/压缩比/质量变化 | INT8(q8) vs FP32：90,387,606 B → 22,972,370 B，压缩比 **3.935×**（−74.6%）；Recall@5 0.7083→0.6806，nDCG@5 0.7596→0.7428 如实记录 | `TECHNICAL_OVERVIEW.md` §2/§5、`benchmark/results.json` | 通过 |
| 2.2-4 WebGPU 优先、显式配置、不支持自动降级 WASM、界面提示 | `probeWebGPU()` 真实 `requestAdapter()`；推理成功才标记已验证；UI 状态栏显示后端；本机 WebGPU 不可用，如实显示 wasm | `frontend/src/embedding.ts`、`frontend/src/App.tsx`、`TEST_REPORT.md` 未通过项 | 通过（降级路径实测；WebGPU 环境受限如实记录） |
| 2.3-1 seekdb-js 接入，存向量/原文/ID/元数据 | seekdb 1.4.0 Embedded；`VectorIndexConfig`(384, cosine, `embeddingFunction:null`) + `FulltextIndexConfig('ik', smart)` | `backend/src/db.js`、`TECHNICAL_OVERVIEW.md` §4 | 通过 |
| 2.3-2 混合检索由 seekdb 完成，不客户端拼接 | `collection.hybridSearch()` → `seekdb::DBMS_HYBRID_SEARCH` | `evidence/stage2_api_smoke.log`、`evidence/browser/browser-test.log` | 通过 |
| 2.3-3 写入与索引刷新，新文档可检索 | 增量导入后 `refresh_index()` | `evidence/stage2_api_smoke.log`、`evidence/kb-isolation.log` | 通过 |
| 2.3-4 增量写入、集合/会话状态正确 | 知识库 A/B 隔离 + 切换恢复 | `tests/kb-isolation.test.mjs`、`evidence/kb-isolation.log`（11/11） | 通过 |
| 2.4 基础性能优化与优化前后实测 | 三配置基准（FP32/WASM、INT8/WASM、INT8 降级），5 次重复中位数，分阶段计时 | `tests/run-benchmark.mjs`、`benchmark/results.json`、`evidence/benchmark/*.json` | 通过 |
| 2.5 Chrome/Edge 可运行 | Chrome（Playwright 1.65.1 headless）实测；Edge 已安装 | `evidence/browser/browser-test.log` | 通过 |
| 2.5 禁止云端推理 API / 服务端预计算回放 | 外部请求数 0；Node 只接收浏览器算好的向量 | `evidence/browser/browser-test.log`、`frontend/src/api.ts` | 通过 |
| 2.5 存储与检索只用 seekdb | 无其他数据库/客户端内存检索 | `backend/src/db.js` | 通过 |
| 3.2 固定条件、压缩比公式、Recall@K/nDCG@K、分阶段计时、首次/预热区分、重复取中位数、降级路径验证 | 全部按要求记录，含未改善/下降项 | `TECHNICAL_OVERVIEW.md` §5、`benchmark/results.json` | 通过 |
| 4.1 可运行 Web 应用 + 启动说明 + 后端显示 | `README.md` §6/§7；UI 显示推理后端 | `README.md`、`evidence/browser/app-wasm.png` | 通过 |
| 4.2 完整源码、依赖配置、模型获取/量化步骤、表结构与索引配置、复现数据 | 全部随仓库提供 | `README.md` §3–§5、`TECHNICAL_OVERVIEW.md` §4、`benchmark/dataset.mjs` | 通过 |
| 4.3 一页技术说明（模型量化/端侧运行/seekdb/状态与优化） | 单文件覆盖四方面 | `TECHNICAL_OVERVIEW.md` | 通过 |

## 5. 最终提交材料清单

**必交（官方 4.1–4.3）**

- `stepfun/frontend/`、`stepfun/backend/`、`stepfun/package.json` 等：可运行 Web 应用与完整源码
- `stepfun/frontend/public/models/`：本地 ONNX 模型（FP32 + INT8），clone 后离线可运行
- `stepfun/frontend/public/ort/`：本地 ONNX Runtime WASM，避免 CDN（满足"禁止云端"）
- `stepfun/README.md`：依赖、安装、seekdb 启动、完整启动、测试、重置、已知限制
- `stepfun/TECHNICAL_OVERVIEW.md`：一页技术说明
- `stepfun/SUBMISSION.md`：本核对清单

**附加证据（官方允许"技术说明之外可附测试日志和详细复现步骤"）**

- `stepfun/TEST_REPORT.md`：10 项测试的命令/退出码/环境/结果，含未通过项
- `stepfun/PROGRESS.md`：10 阶段真实进度
- `stepfun/evidence/`：stage1 环境/模型/seekdb 探测、API 冒烟、浏览器测试、隔离测试、复现检查日志，及 `browser/app-wasm.png` 真实截图
- `stepfun/evidence/benchmark/*.json` + `stepfun/benchmark/results.json`：原始性能数据与中位数
- `stepfun/backend/evidence/`：服务端 seekdb 操作与心跳日志
- `stepfun/scripts/verify-fresh.mjs`：干净环境复现检查（30/30）

## 6. 已知限制（如实，不影响提交完整性）

- WebGPU 在本机 headless Chrome 中 `navigator.gpu.requestAdapter()` 返回 null，真实 WebGPU 路径未能验证；应用已实现并实测 WASM 降级，UI 如实显示后端。
- seekdb 原生 addon 需动态 import、日志写文件、低频心跳保持稳定（已固化在代码中，见 README §10）。
- INT8 的 Recall@5 略低于 FP32，已如实报告，未声称质量提升。

## 7. 提交前自检

```bash
cd D:/OceanBase_WorkBuddy/StepFun_2026
git status --short --branch     # 期望：工作区干净
node stepfun/scripts/verify-fresh.mjs   # 期望：30/30 PASS
```

**本交付未执行任何远程仓库推送，未创建任何 Pull Request。**
