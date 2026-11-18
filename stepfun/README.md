# StepFun 迷你知识库 — 2026 OceanBase 数据库大赛

浏览器本地 AI 推理（Transformers.js）+ seekdb 混合检索的迷你知识库 Web 应用。

**核心流程：** 导入文本文档 → 浏览器本地 embedding → seekdb 存储 → seekdb 数据库端向量与全文混合检索 → 展示排序结果。

> 全部向量在浏览器本地计算，Node 服务端不生成向量；混合检索由 seekdb 数据库端 `DBMS_HYBRID_SEARCH` 执行，不在应用层拼接结果。

## 1. 系统要求

- Windows 11（本机实测 build 26200）；Node.js ≥ 20（实测 v22.22.2），npm ≥ 10
- Google Chrome 或 Microsoft Edge（本机实测 Chrome，Playwright 驱动）
- 磁盘：约 1.5 GB（seekdb 原生库 331MB + 数据库初始化 161MB + 模型 113MB + ORT WASM 53MB）
- 网络：首次安装依赖与下载模型需要网络；`huggingface.co` 主站若不可达，用 `hf-mirror.com` 镜像（模型已随仓库下载到 `frontend/public/models/`，运行时完全离线）

## 2. 依赖版本（真实安装版本）

| 组件 | 版本 |
|---|---|
| Node.js | v22.22.2 |
| React | 19.1.1 |
| Vite | 7.1.7 |
| TypeScript | 5.9.2 |
| @huggingface/transformers | 4.3.2 |
| seekdb | 1.4.0（`@seekdb/js-bindings` 1.4.0，Windows x64 原生） |
| Express | 4.21.2 |
| @playwright/test | 1.65.1 |

## 3. 目录结构

```
stepfun/
  README.md                本文件
  TECHNICAL_OVERVIEW.md    一页技术说明
  PROGRESS.md              分阶段真实进度
  frontend/                React + TS + Vite 前端
    public/models/         本地 embedding 模型（含 FP32/INT8 两份 ONNX）
    public/ort/            本地 ONNX Runtime WASM 运行时（禁止 CDN）
    src/                   前端源码（embedding/api/App/benchmark）
    benchmark.html         基准测试页面
  backend/                 Node.js API 服务（Express + seekdb-js）
    src/db.js              seekdb 封装（不生成向量）
    src/server.js          HTTP API（动态 import + 心跳，见技术说明）
    scripts/api-smoke.mjs  API 冒烟测试
  benchmark/               评测集与结果
  tests/                   Playwright 自动化测试
  scripts/                 辅助脚本（ORT 资产复制等）
  evidence/                真实测试日志与截图
```

## 4. 安装命令

```bash
# 1) 后端依赖
cd stepfun/backend
npm install                    # .npmrc 已设 legacy-peer-deps=true

# 2) 前端依赖
cd ../frontend
npm install

# 3) 复制 ONNX Runtime WASM 运行时到 public/ort（避免 CDN）
cd ..
node scripts/copy-ort-assets.mjs

# 4) 测试工具（仓库根 stepfun/）
npm install -D @playwright/test@1.65.1
```

模型文件已随项目置于 `frontend/public/models/all-MiniLM-L6-v2/`，无需运行时下载。若需重新获取：

```bash
# 用 hf-mirror.com 镜像（huggingface.co 主站在部分网络不可达）
BASE=https://hf-mirror.com/Xenova/all-MiniLM-L6-v2/resolve/main
mkdir -p frontend/public/models/all-MiniLM-L6-v2/onnx
curl -L $BASE/config.json -o frontend/public/models/all-MiniLM-L6-v2/config.json
curl -L $BASE/tokenizer.json -o frontend/public/models/all-MiniLM-L6-v2/tokenizer.json
curl -L $BASE/tokenizer_config.json -o frontend/public/models/all-MiniLM-L6-v2/tokenizer_config.json
curl -L $BASE/special_tokens_map.json -o frontend/public/models/all-MiniLM-L6-v2/special_tokens_map.json
curl -L $BASE/onnx/model_quantized.onnx -o frontend/public/models/all-MiniLM-L6-v2/onnx/model_quantized.onnx
curl -L $BASE/onnx/model.onnx -o frontend/public/models/all-MiniLM-L6-v2/onnx/model.onnx
```

## 5. 模型下载与量化方式

- 模型：`Xenova/all-MiniLM-L6-v2`（`sentence-transformers/all-MiniLM-L6-v2` 的 ONNX 版），许可证 **Apache-2.0**，维度 **384**
- **非量化基线**：`onnx/model.onnx`，FP32，90,387,606 字节
- **INT8 量化**：`onnx/model_quantized.onnx`，ONNX 动态量化（q8），22,972,370 字节
- **压缩比 3.935×（体积减少 74.6%）**
- 量化配置在前端通过 `pipeline(..., { dtype: 'q8' | 'fp32' })` 切换

## 6. seekdb 启动方法

采用 **seekdb Embedded 模式**（无需独立部署服务进程）：

```bash
cd backend
npm run init     # 首次预初始化数据库目录（约 3-4 秒，生成 data/seekdb）
npm start        # 启动 API 服务，监听 127.0.0.1:8787
```

原生库由 `@seekdb/js-bindings` 首次运行时自动下载到 `~/.seekdb/bindings`（Windows x64，约 331MB）。

> **重要**：数据库目录 `backend/data/seekdb` 用 `run/seekdb.pid` 防止多进程同时打开。请确保同一时刻只有一个服务进程访问该目录；重启前先停止旧进程。

## 7. 项目启动方法（完整）

```bash
# 终端 A：API 服务（保持运行）
cd stepfun/backend && npm start

# 终端 B：前端开发服务器
cd stepfun/frontend && npm run dev
# 浏览器打开 http://127.0.0.1:5173/
```

Vite 已配置 `/api` 代理到 `127.0.0.1:8787`。生产构建：`cd frontend && npm run build`。

## 8. 测试命令

```bash
cd stepfun

# API 端到端冒烟（需服务已启动）
node backend/scripts/api-smoke.mjs

# 真实浏览器测试（需前端+服务已启动）
node tests/browser-embedding.spec.mjs

# 三配置性能与质量基准（需前端+服务已启动）
node tests/run-benchmark.mjs
```

所有测试日志标注了命令、退出码、环境与代码版本，见 `evidence/`。

## 9. 重置方法

```bash
# 重置数据库（会清空所有知识库数据）
cd stepfun/backend
# 先停止服务进程，再：
rm -rf data/seekdb && mkdir -p data
npm run init && npm start
```

前端 UI 无需重置；切换知识库会清空当前会话的检索状态。

## 10. 已知限制

1. **WebGPU**：本机 headless Chrome 环境 `navigator.gpu.requestAdapter()` 返回 null（"No available adapters"），WebGPU 推理**未能在本环境验证**。应用已实现 WebGPU 优先 + WASM 自动降级，且强制 WebGPU 时会经实际推理验证后才标记"已验证"；本环境如实显示 WASM。**不伪造 WebGPU 成功结果**。
2. **seekdb 原生 addon 的工程约束**（实测）：
   - 必须用动态 `import()` 加载 seekdb（静态 import 会导致 Express HTTP 无响应）
   - 日志只写文件不写 stdout（后台任务输出管道写满会阻塞事件循环）
   - 需一个非 unref 的低频心跳定时器保持事件循环稳定
   - 这些已固化在 `backend/src/server.js` 与 `db.js` 中
3. **npm 安装**：seekdb 的 peer 依赖用 pnpm `workspace:*` 协议，`.npmrc` 设置 `legacy-peer-deps=true` 绕过（本项目不需要 default-embed，向量在浏览器生成）。
4. **模型仓库**：`hf-mirror.com` 镜像可用，`huggingface.co` 主站在本机不可达；模型已随项目下载，运行时零外网请求。
