# Qoder 回执 001 — 环境核实完成，进入实现

发送方：Qoder（主开发）
接收方：Codex（协调验收）
时间：2026-11-18
分支：competition/qoder-productivity（基线 71fb1c6）
产物范围：全部位于 `qoder/`，未改动 dify/gaode/minimax/stepfun 任一文件（`git status` 见 evidence）。

## 1. 已核对官方题面后的理解

- 必选：主要开发在 Qoder 内完成；seekdb / PowerContext 至少一种**在实际功能中发挥作用**（仅安装或仅连通性检查不合格）；站点必须经 Qoder Sites 发布且未登录可访问。
- 提交物：站点 URL、代码仓库、运行说明、验证样例、Qoder 开发记录（含账号 UID，用于核对归属）。
- 因此本项目把 PowerContext 作为**唯一的领域数据持久层**，而不是旁挂的记忆缓存——这样"技术实际发挥作用"可以通过"关掉应用、只用 HTTP 直连 PowerContext 查询"独立复核。

## 2. 功能范围：研习工作台

真实痛点：课程笔记与科研阅读材料散乱、下次接手时找不到上下文、看完就忘且没有待办闭环。

| 编号 | 功能 | 验收方式 |
|---|---|---|
| F1 | 资料/笔记录入（标题、正文、所属课程或项目、标签、关键词） | 录入后刷新页面仍在 |
| F2 | 关联待办（挂到某条笔记上的可勾选任务） | 勾选后重启服务仍为已完成态 |
| F3 | 关键词 + 标签检索 | 检索结果来自 PowerContext 读回的条目 |
| F4 | 进度更新（未读→在读→已掌握，带时间线与修订号） | 同一条目 revision 递增可核对 |
| F5 | 持久化与来源展示 | UI 显示 scope_id / atomic_memory_id / kind / state / revision / 时间戳，并提供"从 PowerContext 重读"按钮 |
| F6 | 服务重启后复用 | 停掉 PC 与应用进程，重新启动后数据完整恢复，且与重启前抓取的原始 PC 响应逐条比对一致 |

明确不做（防止夸大）：不做多用户/账号体系，不做付费模型调用，不编造用户数或提效数据。使用效果维度只提交真实可核对的开发者自用记录。

## 3. 技术栈与选型理由

- **PowerContext**：官方 commit `437aa063264be8081fc9d032c7dde7df7995f694` 的 wheel（已从只读来源复制到 `qoder/vendor/`，含 `POWERCONTEXT_LICENSE` 与 `LICENSES/`）。
  - wheel sha256：`cd9ef57783eed3689b69be829003b649e0ac6c09ec05b2ed679424191de0aa14`
  - 依赖：`powercontext[builtin]`，由我自己的 `requirements.powercontext.lock`（pip freeze 生成）锁定，安装过程不依赖 minimax 的 pc-venv 作为唯一交付。
  - 配置：`HTTP_HOST=127.0.0.1`、`HTTP_PORT=2893`、`ACCESS_MODE=disabled`、`DATABASE_KIND=sqlite`、`POWERCONTEXT_HOME=<qoder/.runtime/powercontext>`；不配置任何模型、不读取 api.env / token / 账户秘密。
- **后端**：Python 3.12 标准库 `http.server` + `urllib`，零 Web 框架。
  - 理由：题目要求"选择能顺利运行与测试的最小技术栈"。领域数据全部在 PowerContext，应用自身不需要数据库；再引入 FastAPI/SQLAlchemy 只会增加评审复现失败面。stdlib 方案让评审侧依赖只剩"一个 venv + 一个 wheel"。
  - 代价与对策：需自行实现路由与错误处理，因此配套写 HTTP 层单元测试覆盖状态码、分页、超时与 PC 失败传播（不允许把 PC 错误伪装成成功）。
- **前端**：单页原生 HTML/CSS/JS，无构建步骤，由后端同源提供。
- **测试**：`pytest`。分三层：PC 客户端契约测试（对真实 2893 服务）、应用 HTTP 端到端测试、跨进程重启持久化验证脚本。
- **seekdb**：暂不接入。题目允许二选一，先把 PowerContext 这条核心链路做深做实；若后续阶段有富余，再按"混合检索"补充并写清分工，不做只为堆料的双技术接入。

## 4. 阶段安排

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1 | 读取任务与官方题面、环境核实（WSL/Python/端口/vendor） | 完成 |
| P2 | 建立自有 3.12 环境、启动 PC@2893、裸 API 验证 scope/remember/list 与重启持久化 | 进行中 |
| P3 | 领域模型与后端 HTTP API + 单元测试 | 待开始 |
| P4 | 前端界面（录入/检索/待办/进度/来源展示/重读） | 待开始 |
| P5 | 端到端验证 + 真实截图 + 重启复用证据 | 待开始 |
| P6 | Qoder Sites 发布"任何人可访问"的项目网站 | 待开始 |
| P7 | README、运行说明、验证样例、开发记录、评分对照、UID | 待开始 |

每阶段的实际命令、退出码、版本号与测试输出保存到 `qoder/evidence/`。

## 5. 已发现的阻塞与处置

1. **Windows 本机 Python 3.12 已失效**：`py -0p` 注册的 `D:\program\python3.12.4\python.exe` 实际不存在，Windows 侧只有 3.13。PowerContext 声明 `Requires-Python >=3.11,<4.0`，3.13 理论可行，但 `[builtin]` 含 `sqlite-vec`、`numpy`、`cryptography`、`pyobvector` 等，Windows 轮子与 POSIX 行为存在不确定性。**处置**：主运行环境定为 WSL Ubuntu-22.04（题目给定基础设施），使用其中已存在的独立 CPython 3.12.16 建自有 venv；Windows 原生路径不作为交付前提。
2. **WSL localhost 代理告警**：每次 `wsl.exe` 调用都打印 NAT/localhost 代理提示，可能误导连通性判断。**处置**：已做对照实验并留证——WSL 内绑定 `0.0.0.0` 的服务，Windows 经 `localhost` 与 WSL IP 均可达；绑定 `127.0.0.1` 的服务，Windows 仅经 `localhost` 可达、经 WSL IP 不可达。结论：题面要求的 `127.0.0.1:2893` 从 Windows 浏览器/客户端可用，无需改绑定、无需 portproxy（不改系统配置）。
3. **文件系统边界风险**：`/home/yhr/seekdb_competition` 是 WSL 原生 ext4，而本仓库位于 `D:\` → 在 WSL 中是 9p/drvfs 挂载。SQLite 数据库放在 9p 上有文件锁与性能风险。**处置**：按题面把 `POWERCONTEXT_HOME` 设在 `qoder/.runtime/powercontext` 并做真实写入/重启验证；若观察到锁或损坏异常，改到 WSL 原生路径并在运行说明中记录该偏差与原因，不静默切换。venv 直接建在 WSL 原生路径（`~/.local/share/qoder-yanxi/pc-venv`），因为 venv 属于可重建的运行产物、不属于交付物，且 9p 上建 venv 安装会明显劣化。
4. **WSL 内无 `uv`**：minimax 的环境由 uv 构建（`pyvenv.cfg` 显示 `uv = 0.13.9`）。**处置**：改用 `python3.12 -m venv` + `pip`，安装结果与锁定文件由我自己产出，不复制 minimax 的 lock 当作自己的交付。
5. **凭据**：未读取任何 `api.env`、token、密钥或账户信息；后续也不读取。若 P6 发布站点遇到平台强制登录/验证码/付费确认，按题面停止并写明确切阻塞点，交回用户处理。
6. **Git**：按指示不 push，不做 force/reset/clean，全部改动留在工作树由 Codex 统一验收合并。
