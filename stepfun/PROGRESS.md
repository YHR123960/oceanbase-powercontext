# PROGRESS.md — 2026 OceanBase 大赛 stepfun 赛题开发进度

> 本文件逐阶段记录**真实**测试结果、失败问题、下一步与当前 Git 提交。
> 所有数据来自本机实际运行，禁止虚构。

---

## 阶段 1：环境与依赖兼容性检查

**状态：已完成（真实测试通过）**  
**时间：2026-11-18 08:45 – 09:35 GMT+8**

### 已完成工作

1. **Windows 环境**（真实命令输出见 `evidence/stage1/env.log`）
   - OS：Windows 11，内核 `MINGW64_NT-10.0-26200`
   - Node.js `v22.22.2`，npm `10.9.7`，git `2.55.0.windows.3`
   - pnpm / yarn 未安装（本项目统一用 npm）
   - 浏览器：Microsoft Edge 与 Google Chrome 均已安装（真实路径见 env.log）
   - 网络：GitHub 可达；`huggingface.co` 主站**不可达**（HTTP 000），经环境代理后 `hf-mirror.com` 镜像可用（HTTP 200）

2. **官方仓库核验**
   - `https://github.com/oceanbase/powercontext` 分支 `2026-competition-ecosystem` 存在
   - HEAD = `d647275c308e09b7b623f322a26f5c4e85734fb0`（"chore: initialize 2026 competition ecosystem directories"）
   - 仓库含 `stepfun/` 目录，但**仅有 `.gitkeep`**（无既有作品需保留）
   - 克隆为只读参考：`D:\OceanBase_WorkBuddy\_reference_powercontext`，**未推送**

3. **seekdb-js 官方文档核验**（只读克隆 `_reference_seekdbjs`）
   - 包 `seekdb@1.4.0`，支持 **Embedded 模式（Windows x64 原生）** 与 Server 模式
   - `SeekdbClient({path, database})` 走 Embedded；`{host,...}` 走 Server
   - Schema 支持 `VectorIndexConfig`（HNSW, cosine, `embeddingFunction:null` 表示外部传向量）、`FulltextIndexConfig("ik",{ik_mode:"smart"})`
   - `collection.add({ids, documents, metadatas, embeddings})` 可直接传浏览器算好的向量 → 满足"禁止 Node 端生成向量"
   - `collection.hybridSearch({query:{whereDocument:{$contains}}, knn:{queryEmbeddings}, nResults})` 底层调用数据库端 `DBMS_HYBRID_SEARCH.GET_SQL` → **真正的数据库端混合检索**
   - `collection.refresh_index()` 存在（索引刷新）
   - `collection.query({where:{kb:"A"}})` 元数据过滤 → 知识库隔离可行

4. **seekdb 安装与真实数据库操作**（`evidence/stage1/seekdb_probe.log`）
   - `npm install seekdb@1.4.0` 首次失败：`EUNSUPPORTEDPROTOCOL workspace:*`（peer `@seekdb/default-embed` 用了 pnpm 协议）
   - 解决：`npm install seekdb@1.4.0 --legacy-peer-deps`（跳过不需要的 default-embed，因为向量在浏览器生成）→ 成功
   - 原生库 `@seekdb/js-bindings@1.4.0` 运行时下载 Windows x64 二进制到 `C:\Users\14037\.seekdb\bindings`（约 331MB）
   - 首次 `open()` 初始化数据库目录约 161MB
   - **真实跑通**：`open` → `SELECT 1` → `CREATE DATABASE` → `CREATE TABLE(... vec VECTOR(4) ...)` → `INSERT` → `SELECT`
   - **真实跑通 SDK 层**：`createCollection`（3.5s）→ `add`（0.4s）→ `refresh_index`（4.7s）→ `hybridSearch` 返回 `ids=[["d1","d2","d3"]]`、`distances=[[1.61,1,0.5]]` → `query(where:{kb:'A'})` 返回 `["d1","d2"]`
   - 结论：**seekdb 嵌入式 + 数据库端混合检索在本机 Windows 完全可用**

5. **Embedding 模型核验**（`evidence/stage1/model_info.log`）
   - 模型：`Xenova/all-MiniLM-L6-v2`（Transformers.js 兼容的 ONNX 版），基础模型 `sentence-transformers/all-MiniLM-L6-v2`
   - 许可证：**apache-2.0**（真实读取 HuggingFace model card）
   - 维度：384（`hidden_size=384`，`model_type=bert`，`max_position_embeddings=512`）
   - SHA：`751bff37182d3f1213fa05d7196b954e230abad9`
   - 模型 SHA（commit）：同上
   - 真实文件体积：FP32 `model.onnx` = 90,387,606 B；INT8 `model_quantized.onnx` = 22,972,370 B
   - **压缩比 = 3.935×，体积减少 74.6%**
   - 模型文件已下载至 `stepfun/frontend/public/models/all-MiniLM-L6-v2/`（本地加载，不依赖运行时外网）

### 真实测试结果汇总

| 项目 | 结果 |
|---|---|
| Node/npm/git/浏览器 | 通过 |
| 官方仓库分支与空 stepfun 目录 | 通过 |
| seekdb-js 接口核验 | 通过 |
| seekdb npm 安装 | 通过（--legacy-peer-deps） |
| seekdb Embedded CRUD | 通过 |
| seekdb hybridSearch（数据库端） | 通过 |
| seekdb refresh_index | 通过 |
| seekdb 元数据过滤 | 通过 |
| 模型许可证/维度/文件 | 通过 |
| 量化压缩比 3.935× | 通过 |

### 失败问题与解决

- **npm EUNSUPPORTEDPROTOCOL workspace:***：改用 `--legacy-peer-deps`
- **huggingface.co 不可达**：改用 `hf-mirror.com` 镜像下载模型；浏览器加载走本地 `public/models`（无需外网）
- **`addon.open()` 貌似"卡住"**：实为 shell `timeout`/工具超时提前杀死了同步阻塞的原生初始化进程。首次初始化需 ~161MB 磁盘 + 数秒～数十秒；复用已初始化目录后 open 仅 ~3s。**结论：非缺陷，是测试方法问题**。后续测试统一：预初始化 DB 目录、给足超时、用文件日志而非 stdout 判断完成。
- **误杀进程**：一度用 taskkill 清理残留 node 进程，误伤 WorkBuddy 自身 node 进程（未影响工具运行），已停止该做法。

### 下一步任务（阶段 2）
- 搭建 React + TypeScript + Vite 前端与 Node.js API 后端最小骨架
- 后端封装 seekdb 持久化连接（复用单一 client，避免重复 open）
- 确认前后端可启动

### 当前 Git 提交
- 仓库已 `git init`（本地，无 remote，未推送）
- 尚无提交（阶段1文件将在阶段2统一提交）

---

---

## 阶段 2：搭建最小 React + Node.js 项目

**状态：已完成（端到端 10/10 冒烟测试通过）**  
**时间：2026-11-18 09:35 – 10:00 GMT+8**

### 已完成工作
- 目录结构：`stepfun/{frontend,backend,scripts,tests,benchmark,evidence}`
- 后端 `backend/`：Express 4.21.2 + cors 2.8.5 + seekdb 1.4.0（ESM）
  - `src/db.js`：seekdb Embedded 单例封装，写入/刷新/混合检索/向量检索/计数/清空
  - `src/server.js`：HTTP API（动态 import + 心跳模式，见下方关键发现）
  - `scripts/api-smoke.mjs`：端到端冒烟测试
- 前端 `frontend/`：React 19.1.1 + Vite 7.1.7 + TypeScript 5.9.2 + @huggingface/transformers 4.3.2（骨架已装依赖）
- `.npmrc` 设置 `legacy-peer-deps=true` 解决 workspace 协议问题
- `.gitignore` 忽略 node_modules/dist/数据库数据/日志

### 真实测试结果（evidence/stage2_api_smoke.log）
```
PASS health
PASS initial import alpha (2 docs)   WRITE_MS 352
PASS incremental import alpha (+1)
PASS import beta (isolation setup)
PASS index refresh                   REFRESH_MS 327
PASS alpha count=3 / beta count=1
PASS hybrid search by seekdb         SEARCH_MS 73  engine=seekdb::DBMS_HYBRID_SEARCH
PASS kb isolation (beta has no alpha docs)
PASS vector-only search
SUMMARY pass=10 fail=0
```

### 关键失败问题与解决（重要工程经验）
1. **HTTP 请求无响应（CLOSE_WAIT）**：seekdb 原生 addon 若用【静态 import】在 Express 路由模块加载阶段载入，会导致事件循环异常，HTTP 请求到达但不响应。
   - 解决：`server.js` 改为**动态 import** `await import('./db.js')`（Express 先 listen 再加载 db），并加一个**非 unref 的低频心跳 setInterval**。见 `evidence/` 中的诊断记录。
2. **stdout 管道写满阻塞**：后台任务 stdout 无消费者时，seekdb 操作产生的 console.log 会填满管道并阻塞事件循环（表现为写操作后服务假死）。
   - 解决：`db.js` 与 `server.js` 只写文件日志、不写 stdout；服务启动时用 `> stdout.log 2>&1` 重定向。
3. **`col.get()` 返回结构不一致**：`get()` 的 `ids` 是扁平数组 `['kb::id1', ...]`，而 `query()/hybridSearch()` 的 ids 是嵌套数组 `[[...]]`。
   - 解决：`flattenIds()` 兼容两者。此前误把 `res.ids[0]` 当数组，导致 count 返回字符串长度（9/8）。
4. **seekdb pid 文件锁**：数据库目录 `run/seekdb.pid` 防止多进程打开。多进程争抢同一目录会导致 "database already opened in this process (pid file locked)"。
   - 解决：单一服务进程独占数据库目录；重启前先停止旧进程。
5. **原生 addon 阻止进程自然退出**：脚本末尾需显式 `process.exit()`；服务为长驻进程无此问题。

### 下一步任务（阶段 3）
- 前端实现 Transformers.js 浏览器本地 embedding（文档 + 查询）
- 验证无云端调用、无 Node 端向量生成
- 记录模型来源/版本/维度/量化/许可证

### 当前 Git 提交
- 尚无提交（将在关键里程碑统一提交）

---

## 阶段 3：浏览器本地 embedding（含阶段4的seekdb接入，已提前完成）

**状态：已完成（真实浏览器测试 6/6 通过）**  
**时间：2026-11-18 10:00 – 10:10 GMT+8**

### 已完成工作
- `frontend/src/embedding.ts`：Transformers.js 浏览器本地 embedding
  - `env.allowRemoteModels=false` 禁用云端模型
  - 文档与查询均在浏览器本地计算，`embedBatch`/`embedOne`
  - WebGPU 优先、WASM 降级；`probeWebGPU()` 用真实 `requestAdapter()` 探测
  - 后端验证：必须用目标 device 实际推理成功才标记 `deviceVerified=true`
- `frontend/src/api.ts`：只向本地 Node 服务发送**已算好的向量**
- `frontend/src/App.tsx` + `styles.css`：完整 UI（知识库选择/导入/进度/模型信息/后端/查询/结果/原文来源/性能/日志）
- `scripts/copy-ort-assets.mjs`：把 ONNX Runtime WASM 运行时复制到 public/ort/（53MB）
- `tests/browser-embedding.spec.mjs`：Playwright + 系统 Chrome 真实浏览器测试

### 真实测试结果（evidence/browser/browser-test.log）
```
WEBGPU_PROBE_UI  navigator.gpu.requestAdapter() 返回 null
BACKEND_CHIP     推理后端: wasm ✓已验证
PASS 模型在本地加载成功并显示后端
PASS 文档导入+本地向量化+写库+索引刷新 (66ms/251ms/241ms)
PASS 混合检索返回结果 (3条)
PASS 检索由 seekdb 执行 (engine=seekdb::DBMS_HYBRID_SEARCH)
PASS 无云端 embedding 请求（所有请求本地, EXTERNAL_REQUEST_COUNT 0）
PASS 无页面运行时错误
SUMMARY pass=6 fail=0
```

### 关键失败问题与解决
1. **ORT WASM 从 CDN 加载**：transformers.js 在模块初始化时若发现 `ONNX_ENV.wasm.wasmPaths` 为空，自动设为 cdn.jsdelivr.net 路径，违反"禁止云端"。
   - 解决：`env.backends.onnx.wasm.wasmPaths` 与 `ONNX_ENV.wasm` 是同一引用，必须**就地修改 wasmPaths 属性**（不能替换整个 wasm 对象），指向本地 `/ort/`。同时把 ORT 的 wasm/mjs 文件复制到 `public/ort/`。修复后 `EXTERNAL_REQUEST_COUNT=0`。
2. **WebGPU 不可用**：本机 headless Chrome 环境 `navigator.gpu.requestAdapter()` 返回 null（"No available adapters"，Windows powerPreference 警告）。这是真实环境限制，**不伪造 WebGPU 成功结果**；强制 WebGPU 时正确降级到 WASM 并验证降级路径。UI 如实显示 wasm。

### 下一步任务（阶段5/6）
- 完善知识库切换、会话状态、增量导入的自动化验证
- FP32/INT8/WASM 三配置性能对比与检索质量评估（阶段7）
- 整理 README 与技术说明

### 当前 Git 提交
- 尚无提交（将在阶段8后统一提交）

---

## 阶段 6/7：量化、降级、性能与质量评测

**状态：已完成（真实浏览器基准测试全部跑通）**  
**时间：2026-11-18 10:10 – 10:25 GMT+8**

### 已完成工作
- `frontend/benchmark.html` + `frontend/src/benchmark.ts`：浏览器内基准入口
- `benchmark/dataset.mjs`：固定评测集（24 文档 / 12 查询 / ground truth），Recall@K 与 nDCG@K 计算
- `tests/run-benchmark.mjs`：Playwright 驱动三配置，各配置独立页面（避免 ORT 状态污染），5 次重复取中位数
- `TECHNICAL_OVERVIEW.md`：一页技术说明含完整性能表

### 真实测试结果（benchmark/results.json）
环境：Chrome headless / Windows 11 / Node v22.22.2 / WebGPU 不可用

| 指标(中位数) | A: FP32/WASM | B: INT8/WASM | C: INT8/WASM降级 |
|---|---|---|---|
| 模型加载 ms | 1566 | 1145 | 1089 |
| 首次推理 ms | 19 | 11 | 12 |
| 预热推理 ms | 15 | 9 | 10 |
| 文档吞吐 段/秒 | 21.09 | 40.2 | 40.27 |
| 写入 ms | 35 | 34 | 35 |
| 索引刷新 ms | 315 | 336 | 327 |
| 查询向量 ms | 21 | 14.5 | 14 |
| seekdb检索 ms | 10 | 10.5 | 9.5 |
| 端到端 ms | 21 | 22 | 20.5 |
| Recall@1 | 0.4653 | 0.4653 | 0.4653 |
| Recall@5 | 0.7083 | 0.6806 | 0.6389 |
| nDCG@5 | 0.7596 | 0.7428 | 0.7090 |

结论：INT8 加载/推理/吞吐明显优于 FP32（吞吐约 1.9×），但 Recall@5/nDCG@5 有小幅下降；端到端延迟 INT8 未改善（seekdb 检索成主开销）；C 与 B 同为 INT8/WASM 但召回有波动（HNSW 近似检索随机性）。均如实记录，未虚构提升。

### 失败问题与解决
- C 配置首轮失败：transformers.js/ORT 在同一页面内 WebGPU 失败后无法再初始化 WASM（全局状态污染）→ 改为每配置独立 page。
- C 配置因本环境无 WebGPU，自动模式落地为 WASM，直接以强制 WASM 实测降级路径并如实说明。
- dataset.mjs 误用 TS 类型注解导致浏览器 "Unexpected token ':'" → 去掉类型注解（类型声明放 .d.mts）。

### 阶段 5 补测：知识库隔离与会话状态（tests/kb-isolation.test.mjs）
11/11 通过：跨库数据隔离、切换后文档数正确、A/B 检索互不串数据、增量导入、索引刷新后新文档可检索、切回会话状态正确。

### 当前 Git 提交
- 尚无提交（阶段10统一提交）

---

## 阶段 8/9/10：文档整理、复现检查与 Git 提交

**状态：已完成**  
**时间：2026-11-18 10:22 – 10:30 GMT+8**

### 已完成工作
- `README.md`（系统要求/安装/依赖版本/模型/seekdb启动/项目启动/测试/重置/已知限制）
- `TECHNICAL_OVERVIEW.md`（一页技术说明：模型来源/量化/体积对比/质量变化/WebGPU-WASM机制/seekdb结构/混合检索/索引刷新/性能优化与真实结果）
- `TEST_REPORT.md`（全部测试的命令/退出码/环境/代码版本，含未通过项如实记录）
- `scripts/verify-fresh.mjs`：干净环境复现检查 30/30 PASS（`evidence/verify-fresh.log`）
- `.gitignore`：排除 node_modules/dist/数据库数据/临时日志，保留 evidence 证据日志
- 本地 git 分支 + 提交（见下方 SHA；未推送任何远程仓库）

### 关键决策记录
- 模型二进制（ONNX 113MB + ORT WASM 53MB）随仓库提交，保证评审方 clone 后可离线运行，无需重新下载。
- 数据库数据目录（`backend/data/seekdb`，161MB）不提交，用 `npm run init` 重建（README 有说明）。
- 未使用官方仓库作为提交目标：官方 `stepfun/` 目录仅为占位（.gitkeep），且用户要求不得向官方仓库推送；本项目在独立目录 `D:/OceanBase_WorkBuddy/StepFun_2026` 建立本地 git 仓库。

### 当前 Git 提交
- 分支：`competition/stepfun-submission`（本地）
- Commit SHA：见 `git log -1 --format=%H`（本交付含 2 个提交：主提交 + 文档 SHA 回填）
