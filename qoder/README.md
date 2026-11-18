# 研习工作台（Yanxi Workbench）

课程笔记 / 科研阅读 / 关联待办放在一起，**唯一读写层是 PowerContext 显式 Atomic Memory**：
应用自己不存数据库、不存文件、不缓存，每次界面刷新都重新走 HTTP 读回。

- 公开展示网站（Qoder Sites，未登录可访问）：<https://yanxi-workbench-w90bbjbmep1.qoder.zone>
- 本目录 `qoder/` 即交付物全部代码、脚本、证据与网站源码。

## 1. 它解决什么

读文献、上课、做科研的人普遍有第二套“笔记系统 + 待办系统 + 聊天记录”，三处互相抄。
研习工作台把一条资料当作**可检索的记忆**而不是文件：写入即分块成 Atomic Memory，
标签由服务端保存并可被服务端过滤，检索命中方式（`text` / `tag` / `client-scan`）直接写在界面上，
状态切换（未开始 / 在读 / 已掌握）追加进度记录而不是覆盖历史。

## 2. 快速开始

前置条件：

- Linux 或 WSL2（脚本为 bash），一个 **CPython ≥ 3.11 且 < 4.0** 的解释器（PowerContext 要求；系统自带 3.10 不行）。
  用 `--python` 指定你自己的解释器即可，脚本不下载 Python，也不依赖任何其他项目的目录。
- 无需 API Key、无需模型、无需付费服务：本项目只用显式读写与文本检索，均为确定性能力。

```bash
cd qoder

# 1) 用仓库内 vendor/ 的官方 wheel 建独立环境，并生成依赖锁
bash scripts/setup_pc_env.sh --python /path/to/python3.12
#    环境默认落在 $HOME/.local/share/qoder-yanxi/pc-venv，可用 --venv 改位置

# 2) 启动 PowerContext Server（127.0.0.1:2893，强制 --no-env-file，不加载任何 env 文件）
bash scripts/start_pc.sh

# 3) 灌入初始演示数据（构造样例，见第 6 节）
PYTHONPATH=src python scripts/seed_demo.py

# 4) 启动应用（默认 127.0.0.1:2894）
PYTHONPATH=src python -m yanxi.server
#    浏览器打开 http://127.0.0.1:2894
```

停止服务：`bash scripts/start_pc.sh stop`。日志在 `qoder/.runtime/pc.log`（`.runtime/` 已被 gitignore）。

## 3. 目录结构

| 路径 | 作用 |
|---|---|
| `src/yanxi/pc.py` | PowerContext HTTP 客户端（仅标准库 `urllib`），含调用审计记录 |
| `src/yanxi/store.py` | 领域模型：追加写 + 读取折叠（fold-on-read）、分块、进度排序 |
| `src/yanxi/server.py` | 应用后端：`ThreadingHTTPServer` + `/api/*`，无第三方框架 |
| `web/` | 零构建前端（`index.html` / `app.js` / `styles.css`） |
| `scripts/` | 环境、服务、演示数据、接口核对、重启端到端、锁回放脚本 |
| `tests/` | 37 项 pytest（含对真实 Server 的 9 项） |
| `vendor/` | 官方 wheel + 许可证，保证评审不依赖网络来源 |
| `site/` | Qoder Sites 展示网站源码（发布副本，见第 7 节） |
| `evidence/` | 运行日志、JSON 结果、截图与截图来源说明 |
| `coordination/` | 任务书、官方题面、评审反馈与开发进度 |

## 4. 与 PowerContext 的真实接口

实测对象：官方构建 `0.1.dev1+g437aa0632.d20261118`（commit `437aa0632`，分支 `2026-competition-ecosystem`），
`api_contract_version = {major:1, minor:5}`，启用的特性契约
`access.principal`、`connection.identity`、`memory.explicit`、`scope.selection`。

| 界面动作 | 实际调用 |
|---|---|
| 首次进入 / 切换工作区 | `POST /v1/scopes`（幂等，标题键 `qoder-yanxi-workbench:<workspace>`） |
| 保存笔记 / 待办 / 进度 | `POST /v1/memory/remember`（`kind=yanxi.note.v1` 等，追加新记录，`seq` 递增） |
| 刷新界面 | `POST /v1/atomic-memory/list`（游标翻页读完全部记录，读取时按 `entity_id` 折叠） |
| 关键词检索 | `POST /v1/atomic-memory/search`，`mode=text` |
| 标签过滤 | 标签写在 `PUT /v1/scopes/{id}/artifacts/{family}/{artifact_id}/tags`（带 `If-Match`），过滤走服务端 `list_atomic` |
| 数据来源面板 | `GET /v1/server-info`、`GET /v1/capabilities` |

遵守的硬限制：单条 `remember.text` ≤ 8192 UTF-8 字节（应用预算 7600，超长正文自动分块并按 `chunk_index` 无损拼回）；
每个 artifact ≤ 32 个标签、单次查询 ≤ 16 个标签、标签 ≤ 64 字符；`limit` ≤ 100 且必须跟游标。
官方契约禁止就地改写记忆条目，因此删除实现为追加一条 `op=retire`，旧记录永远可查。

进度时间线排序：`（时间戳，笔记修订号 note_seq，seq）`。时间戳为微秒精度；同一秒内连续切换状态时，
修订号是决定性次序依据，保证时间线最后一条与卡片当前状态一致（回归测试见
`tests/test_store.py::test_same_second_updates_order_by_note_revision`、
`tests/test_live_powercontext.py::test_same_second_status_changes_order_by_revision_on_the_server`）。

## 5. 验证与证据

| 项 | 命令 | 结果 | 证据文件 |
|---|---|---|---|
| 环境与接口核对 | `python scripts/verify_pc.py` | 12 项全部 PASS | `evidence/p2_pc_verify.json` |
| 自动化测试 | `PYTHONPATH=src python -m pytest -q -rA` | 37 项通过（19 领域模型 / 9 HTTP 接口 / 9 真实 Server） | `evidence/p3_pytest_output.txt`、`evidence/p3_pytest_junit.xml` |
| 重启后数据仍在 | `python scripts/e2e_restart.py` | 10 步通过，写→杀进程→重启→摘要一致 | `evidence/p5_e2e_restart.json` |
| 依赖锁可复现 | `bash scripts/replay_lock.sh` | 全新 venv 装 122 项锁定依赖 + vendored wheel，`powercontext --version` 成功 | `evidence/p1_lock_replay.log` |
| 界面截图 | 见 `evidence/screenshots/capture_manifest.json` | 4 张 1600×1000 真实运行截图 | `evidence/screenshots/` |
| 独立验收 | Codex 复核 | 34 项基线 + 时间线复核 + 换路径全新安装 | `evidence/codex_*.json` |

证据文件里的 `server_id` 与 `scope_id` 是**该次运行自己**的值：`server_id` 每次启动重新生成，
只有幂等键 `qoder-yanxi-workbench:<workspace>` 解析出的 Scope 才是跨重启复用的身份。
核对当前服务请用 `bash scripts/start_pc.sh status` 与界面“数据来源”面板。

截图说明：`02/03/04` 三张需要把关键词或标签填进搜索框。为不改动交付代码，截图用了 `.runtime/capture/` 下
一份 `web/` 副本，额外加载一个只负责“给原有输入框赋值并调用页面已有的 `runSearch()`”的小脚本；
副本的后端文件与仓库文件 md5 一致，细节写在 `evidence/screenshots/capture_manifest.json`。

## 6. 演示数据是构造样例

`scripts/seed_demo.py` 写入的四条笔记（组会汇报骨架、文献管理、索引选择率、RAG 引用可靠性）
及其标签、待办、进度备注**全部是为演示构造的样例文本**：

- 每条笔记都带 `构造样例` 标签；
- 正文首行写明“（构造样例，非真实反馈）”；
- 进度备注统一带 `构造样例｜` 前缀。

这些文字不代表任何同学的真实反馈，也不是提效数据。本项目尚未开展真实用户试用，
因此不给出“节省多少小时”这类数字；真实使用规模请以后续站点访问统计与实际用户记录为准。

如果这个库之前用旧版脚本初始化过，`seed_demo.py` 会给同名旧笔记**追加一条新修订**补上 `构造样例` 标签，
不会重复写入；但按 PowerContext 的 append-only 契约，旧记录里已经写下的进度备注不会被改写。
要逐字复现第 5 节截图里的演示状态，请用全新的 `POWERCONTEXT_HOME`（默认即首次运行时自动新建）。

## 7. 项目网站

网站源码在 `qoder/site/web/`，由 Qoder Sites 发布：

- 地址：<https://yanxi-workbench-w90bbjbmep1.qoder.zone>
- 可见范围：**任何人都可访问**（`access_mode: public`，未登录、无痕窗口可打开）
- 内容为静态展示站（无后端、无凭据），截图即本仓库 `evidence/screenshots/` 中的同一批文件。

## 8. 评分维度对照

| 维度 | 本项目对应材料 |
|---|---|
| 实用价值 | 学习科研场景的“笔记—待办—进度分散”痛点，第 1 节；界面直接给出检索命中方式 |
| 完成度与体验 | 记录 / 检索 / 标签过滤 / 状态与进度 / 关联待办 / 删除可审计 / 重启恢复，全流程可点 |
| 技术结合 | 第 4 节接口表 + `evidence/p2_pc_verify.json`（12 项真实行为核对）+ 界面“数据来源”面板 |
| 工程质量 | 标准库实现、vendored wheel + 可回放依赖锁、37 项测试、可复现脚本与运行日志 |
| Qoder 开发实践 | `coordination/REPLY_001.md`、`REPLY_002.md`、`PROGRESS.md`、`evidence/communication_001.png`、`evidence/qoder_*.png` |
| 使用效果 | 未开展真实用户试用，第 6 节明确说明，不虚构数据 |

## 9. 边界与不做的事

- 全程 `--no-env-file` 启动 PowerContext，`POWERCONTEXT_ACCESS_MODE=disabled`，不配置任何模型与 Provider；
  开发过程中未读取任何 API Key / Token / `api.env` 等凭据文件。
- 不依赖其他项目的 venv 或解释器路径；环境只从 `vendor/` 与锁文件构建。
- 后端只监听 `127.0.0.1`，不对外暴露端口。

## 10. 提交材料清单

| 材料 | 位置 |
|---|---|
| 项目网站网址 | <https://yanxi-workbench-w90bbjbmep1.qoder.zone>（任何人都可访问） |
| 代码仓库 | <https://github.com/YHR123960/oceanbase-powercontext>，分支 `2026-competition-ecosystem`，本项目资产全部在 `qoder/` 目录 |
| 运行说明 | 本文第 2 节 |
| 验证样例 | 本文第 5 节 + `evidence/`，另见网站“按步骤验证”一节 |
| Qoder 开发记录 | `coordination/`、`PROGRESS.md`、`evidence/qoder_*.png`、`evidence/communication_001.*` |
| Qoder 账号 UID | 提交表单填写**本人阿里云账号 ID**（Qoder CN 个人账号即手机号绑定的阿里云主账号）；完整号码不写入公开仓库 |
| 使用效果材料 | 暂缺，见第 6 节说明 |

关于 “Qoder 账号 UID” 的填写说明（2026-11-18）：

- 大赛《提交材料》与《提交方式》要求填写“Qoder 账号 UID”，用于核对站点归属及使用记录，但未定义该字段的取值来源
  （官方赛题页与《FAQ - 大赛常见问题答疑》均已核对原文）。
- Qoder CN 个人账号以手机号绑定的**阿里云主账号**为主体（<https://docs.qoder.cn/product-overview/account-and-subscription.md>），
  阿里云为每个账号分配的 16 位数字标识即“账号 ID，也叫 Account ID 或 UID”
  （<https://help.aliyun.com/zh/sae/check-account-id>）。**本项目按此口径提交：比赛表单的 Qoder 账号 UID = 本人阿里云账号 ID。**
- 该数值在 Qoder CN 网页端「个人信息」中可见；Qoder 客户端另有「设置 → 个人资料 → 编辑」入口
  （<https://docs.qoder.cn/qoder/sites.md>）。两处数值以账号页面显示为准。
- 账号标识属于个人信息，公开仓库只记录填写口径与来源页面，**不记录完整号码**；核对归属请直接以本仓库作者账号发布的
  Qoder Sites 站点与开发记录截图为准。
