# 研习工作台 — 开发进度

主开发：Qoder　协调验收：Codex
开发分支：`competition/qoder-productivity`；**交付分支：`2026-competition-ecosystem`**（基线 `71fb1c6b9922e599399d2df993ca5d3923182ce8`，
远端 <https://github.com/YHR123960/oceanbase-powercontext>）
所有产物位于 `qoder/`。

| 阶段 | 内容 | 状态 | 证据 |
|---|---|---|---|
| P1 | 任务核对与环境核实 | 完成 | `evidence/p1_environment.txt`、`evidence/p1_lock_replay.log` |
| P2 | 自有 PowerContext 环境 + 服务 + 裸 API 验证 | 完成 | `evidence/p2_pc_verify.json`（12/12） |
| P3 | 领域模型 + 后端 HTTP API + 单元测试 | 完成 | `evidence/p3_pytest_output.txt`、`evidence/p3_pytest_junit.xml`（37 通过 / 0 失败 / 0 跳过） |
| P4 | 前端界面 | 完成 | `web/`、`evidence/qoder_live_ui_stage_005.png` |
| P5 | 端到端验证 + 重启复用 + 截图 | 完成 | `evidence/p5_e2e_restart.json`（10 步）、`evidence/screenshots/`（4 张 1600×1000 + `capture_manifest.json`） |
| P6 | Qoder Sites 公开网站 | 完成 | https://yanxi-workbench-w90bbjbmep1.qoder.zone（`access_mode: public`，未登录 200） |
| P7 | README / 运行说明 / 验证样例 / 评分对照 / UID | 完成（UID 口径由作者确定，见 P10） | `README.md`、`coordination/REPLY_002.md` |
| P8 | REVIEW_001 第 1–4 项整改 | 完成 | 本文件“P8”小节 |
| P9 | 交付清洁性修复 + 最终重跑验证 | 完成 | `evidence/p2_pc_verify.json`（12/12）、`evidence/p5_e2e_restart.json`（10/10）、`evidence/p3_pytest_output.txt`（37 passed） |
| P10 | 最终校验、提交并推送到 `2026-competition-ecosystem` | 完成 | 本文件“P10”小节 |

## P1 环境核实（2026-11-18）

- 仓库基线：`competition/qoder-productivity` @ `71fb1c6b9922e599399d2df993ca5d3923182ce8`，改动范围仅 `qoder/`。
- Windows：Python 3.13.3（`py -0p` 里注册的 3.12.4 目录实际已不存在，不能用于新建环境）、Node v24.14.1。
- WSL：Ubuntu-22.04 运行中，默认用户 `yhr`；系统 python3 为 3.10.12（低于 PowerContext 要求的 `>=3.11`）；存在可用的独立 CPython **3.12.16**；无 `uv`。
- 文件系统边界：`/home/yhr/seekdb_competition` 是 WSL 原生 ext4，本仓库位于 `D:\` → WSL 侧是 9p/drvfs 挂载。
- 连通性对照实验（决定性）：
  - WSL 内绑定 `0.0.0.0:8099` → Windows 经 `localhost` 与 WSL IP 均可达（200/200）。
  - WSL 内绑定 `127.0.0.1:8098` → Windows 经 `localhost` 可达（200），经 WSL IP 不可达（000）。
  - 结论：题面要求的 `127.0.0.1:2893` 无需改绑定、无需 portproxy、无需改系统配置即可从 Windows 访问。

## P2 自有环境与 PowerContext 服务（2026-11-18）

### 交付自足性

- 官方 wheel 与许可证复制到 `vendor/`：`powercontext-0.1.dev1+g437aa0632.d20261118-py3-none-any.whl`
  - sha256 `cd9ef57783eed3689b69be829003b649e0ac6c09ec05b2ed679424191de0aa14`（与来源一致）
  - `vendor/POWERCONTEXT_LICENSE`、`vendor/LICENSES/stopwords.txt` 一并复制
- `scripts/setup_pc_env.sh` 用 vendored wheel 建**全新 venv**并 `pip freeze` 出 `requirements.powercontext.lock`（**123** 项）。安装组合为 `[builtin,server,cli]`：首轮只装 `[builtin]` 时 `powercontext` CLI 因缺 `typer` 直接崩溃，说明 server/cli 是运行服务与命令面的真实依赖，已记录并修正。
- 因此本项目不把 minimax 的 `.runtime/pc-venv` 作为交付前提；复用其独立 CPython 3.12.16 解释器仅作为"提供一个 ≥3.11 Python"的可选来源，运行说明中亦允许评审用任意满足版本的 Python。

### 服务实测

- `scripts/start_pc.sh` 以 `POWERCONTEXT_HOME=qoder/.runtime/powercontext`、`HTTP_HOST=127.0.0.1`、`HTTP_PORT=2893`、`ACCESS_MODE=disabled`、`DATABASE_KIND=sqlite` 启动，并强制 `--no-env-file`：**不发现、不加载任何 env 文件**，从机制上保证不读取任何凭据；未配置任何模型。
- 启动结果：`server_id=c44f83ce-d5db-4933-a321-02ef2c701756`、`package_version=0.1.dev1+g437aa0632.d20261118`、`api_contract_version=1.5`。
  注意 `server_id` 由进程每次启动生成（今日同一份数据三次启动分别报告
  `c44f83ce…`/`673465cf…`/`35a76202…`）；可复用的身份锚是幂等键 Scope，见 P9。
- 能力确认：`atomic_memory.extract` = `disabled / provider_not_configured`，而 `memory.explicit` 契约可用 → 显式 Atomic Memory 读写**不需要付费模型**，与题面预期一致。
- SQLite home 放在 9p 挂载上启动与读写均正常（未见锁错误）；这一点在 P5 的重启验证里继续观察，若出现异常会如实记录并改用 WSL 原生路径。

### 裸 API 验证：12/12 PASS（`scripts/verify_pc.py`）

| 检查 | 实测结果 |
|---|---|
| server_identity | product=powercontext，contract 1.5 |
| explicit_memory_contract_present | feature_contracts 含 `memory.explicit` |
| runs_without_any_model | `atomic_memory.extract=disabled(provider_not_configured)` |
| scope_idempotency | 同 `idempotency_key` 两次创建返回同一 `scope_id`（version=1） |
| atomic_memory_write_readback | 写入返回 `family=atomic-memory`、`artifact_id=art_…`、`revision=1`、`state=active`，文本原样读回 |
| read_back_by_kind | 按 kind 精确读回 1 条 |
| cursor_pagination_complete | `limit=5` 走 3 页取回全部 12 条；helper `limit=100` 同样 12 条（无静默截断） |
| server_side_tag_retrieval | 中文标签入库并可过滤：`tag_match=all` 两标签命中 1 条、未知标签 0 条 |
| server_side_text_search | `mode=text` 命中 1 条，`matched_by=['text']`，RRF score=0.01639 |
| failures_propagate_not_faked | 空文本→422；15000 字节（限 8192）→422；未知 scope→404；均抛 `PCError` 而非返回"空成功" |
| chunking_respects_byte_limit | 超限长文切成 2 块、每块 ≤7600 字节、拼接无损 |
| records_stable_across_reconnect | 重连后 12 条记录仍可读回 |

### 过程中发现并修正的真实契约问题

1. **`If-Match` 是强制的**：`PUT …/tags` 无 ETag 直接 `428 Precondition Required`，ETag 过期 `412`。客户端已改为"读 ETag → 带 If-Match 写 → 412 重试一次"，而不是猜一个 `*`。
2. **`urllib` 的 header 大小写**：`dict(response.headers)` 会丢掉大小写无关语义，导致 ETag 取不到。已加 `header_value()` 做大小写无关查找。
3. **`remember.text` 上限 8192 UTF-8 字节**，`ReviseMemoryEntryRequest.citation` 在官方契约中被标记为"带即拒"（legacy unsupported）→ 无法就地改写同一条记忆。因此领域层采用**追加式事件 + 折叠读**模型（每条记录携带 entity_id / seq），进度与修订历史天然可审计。
4. Git Bash → WSL 的内联引号会吞掉 shell 变量，已统一改为仓库内脚本文件调用（同时也是评审要用的脚本）。

## P3 领域模型与后端（2026-11-18）

- 三类记忆 kind：`yanxi.note.v1`、`yanxi.task.v1`、`yanxi.progress.v1`；全部走 `POST /v1/memory/remember` 追加，
  读取用 `POST /v1/atomic-memory/list` + 游标翻页，再按 `entity_id` 折叠出当前状态（fold-on-read）。
- 应用侧**没有任何缓存、没有本地库文件**：`load()` 每次都重新读服务端，`/api/state` 直接返回折叠结果与记录条数。
- 后端只用标准库（`ThreadingHTTPServer` + `urllib`），前端零构建；因此评审复现不需要 Node 工具链。
- 长正文按 7600 UTF-8 字节预算分块（硬上限 8192），读回按 `chunk_index` 拼接，测试逐字比对。
- 删除 = 追加 `op=retire`，旧记录仍可查回；`tests/test_live_powercontext.py::test_delete_keeps_the_memory_auditable`
  在真实服务上断言同一实体存在 `seq=[1,2]` 且第二条是 tombstone。

## P4 前端界面（2026-11-18）

- 三栏：左写入表单，中列表 + 检索/标签/状态过滤，右详情 + 关联待办 + 进度时间线 + 单条数据来源。
- 顶栏“数据来源”抽屉显示 Server ID、包版本、API 契约、Scope、kind、记录条数，以及**本次刷新真实发生的
  HTTP 调用清单**（方法 / 路径 / 状态码 / 请求与响应字节 / 耗时），用于核对指定技术是否真的在起作用。
- 检索结果卡片带命中方式标记（`text` / `tag` / `client-scan`），提示行写明“服务端命中 N 条记录 · 界面结果 M 条”。

## P5 端到端与截图（2026-11-18）

- `scripts/e2e_restart.py`：自带 workspace 与端口，写入 → 真实 `start_pc.sh stop/start` 重启 → 读回摘要比对，10 步全部通过（`evidence/p5_e2e_restart.json`）。
- 截图为 headless Chrome 1600×1000 真实渲染；SQLite home 放在 9p 挂载上重启未出现锁异常。

## P6 Qoder Sites（2026-11-18）

- 静态展示站（无后端、无凭据）：产品说明、六个能力卡片、四张真实截图 + 图注、按步骤验证表、构造样例声明、评分对照、开发记录。
- 发布链路：`open_design_workbench` 注册 → `prepare_site` → `get_publish_status` → `publish_site` → 状态确认 →
  `update_access_policy(public, confirmPublic)`；两次发布复用同一 Project/Site，未创建替代站点。
- 交付校验：无登录态 `curl` 首页 200，四张 PNG 200 且 md5 与仓库一致；整改后重新发布并复核 `published: true`。

## P8 REVIEW_001 第 1–4 项整改（2026-11-18，详见 `coordination/REPLY_002.md` 第 1–4 节）


1. 锁文件去掉 `file:///mnt/d/...` 绝对 wheel 引用（122 条精确版本、0 条 `file:`），本体改从 `vendor/` 安装。
2. `setup_pc_env.sh` 真正解析 `--python/--venv/-h`（含 `=` 形式与 `PYTHON_BIN`），加 `(3,11)–(4,0)` 版本闸门，
   候选解释器只列通用路径，不依赖 minimax 目录、不下载 Python。
3. 同秒进度顺序：`now()` 微秒精度 + 进度记录写入 `note_seq` + 排序键 `(at, note_seq, seq)`；
   新增 3 项测试：2 项在 `tests/test_store.py`（同秒顺序 + 记录条数，含把服务端返回顺序整体反转的模拟），
   1 项在 `tests/test_live_powercontext.py` 对真实服务写同秒三次状态切换。
   自查另发现并修复 `record_counts.note_records` 被累加器同名覆盖的问题，并加测试锁定。
4. `seed:demo-v2` 把演示数据显式标注为构造样例（标签 / 正文首行 / 进度备注前缀），去掉读起来像真实反馈的措辞，
   演示时间线并入脚本；四张截图按新数据重拍并补 `capture_manifest.json`；README 第 5 节与网站同步声明。
   旧库补标只追加新修订（同名笔记不重复写入）；append-only 契约下已写入的旧备注保持原样，README 已说明。
5. 顺带修复 `replay_lock.sh` 的 glob + extras 引号问题（先解析 wheel 路径再整体加引号），
   全新 venv 重放 `SCRIPT_EXIT=0`，日志见 `evidence/p1_lock_replay.log`。
6. 交付前索引与范围复核：`git status --porcelain` 仅 `qoder/`（62 个待提交文件），无凭据、无 venv、
   `.runtime/` 已忽略；索引保持为空，未 push。证据日志的忽略问题与最后重跑见 P9。

## P9 交付清洁性与最后重跑（2026-11-18，详见 `coordination/REPLY_002.md` 第 8–9 节）

- 修复证据日志被忽略：开发机全局 `core.excludesFile`（`C:/Users/14037/git.ignore`）含 `*.log`，
  会使 `evidence/p1_lock_replay.log` 在 `git add qoder/` 时被静默跳过。`qoder/.gitignore` 加
  `!evidence/*.log` 后，该文件重新出现在 `git status --porcelain -uall qoder` 中（现共 62 个待提交文件）。
- 文档口径统一：README 章节号（截图=第 5 节、构造样例=第 6 节、网站=第 7 节、提交材料=第 10 节）、
  旧库补标行为与 append-only 说明、锁文件数字（122）在 README / PROGRESS / REPLY_002 / 网站四处核对一致。
- 11:28 在同一服务上重跑并刷新证据：`verify_pc.py` 12/12 PASS、`e2e_restart.py` 10/10 PASS
  （真实 stop → 连接被拒 → start，记录 digest 与条数逐项相同）、全量 `pytest` 37 passed。
  两者写入各自幂等键 Scope，演示 Scope 未受影响（4 笔记 / 5 待办，时间线末项与卡片状态一致）。
- 持久身份口径：`server_id` 每次启动重新生成，重启验证的判据是幂等键 Scope 与逐 kind 记录 digest。
- 收尾：截图用的临时应用（2897）已停止，capture 数据目录保留以供追溯；
  2893（重启后 pid 9007）与 2894（pid 8786）按文档口径继续运行。

## P10 最终校验与推送（2026-11-18，作者指示直接执行）

- 交付文件清点：`git status --porcelain -uall qoder` = **62 个文件，全部在 `qoder/` 下**，`qoder/` 以外 0 项改动；
  其余赛题目录（`dify/`、`gaode/`、`minimax/`、`stepfun/`）与 `qoder/.gitkeep` 之外无任何 tracked 变更。
- 敏感内容复查：全目录 `grep` 未见 API Key / Token / 凭据文件；**账号 UID 数值不入仓库**（README 第 10 节只记录填写口径）；
  `.runtime/`（SQLite home、pc.log）已被 `qoder/.gitignore` 排除；`!evidence/*.log` 保证 `p1_lock_replay.log` 随交付提交。
- 推送前重跑（源码与证据未变，仅文档口径调整）：`pytest` **37 通过**（`tests/test_store.py` 19 / `tests/test_server_api.py` 9 /
  `tests/test_live_powercontext.py` 9，对真实 127.0.0.1:2893 服务）；
  服务健康检查 `2893` 与 `2894` 均 HTTP 200；`evidence/p2_pc_verify.json` 12/12、`evidence/p5_e2e_restart.json` 10/10；
  四张截图在 `evidence/screenshots/` 与 `site/web/assets/` md5 逐一对应；站点无登录态 `curl` 首页与图片均 200。
- 提交与推送：本地 `2026-competition-ecosystem` 与 `origin/2026-competition-ecosystem` 同为 `71fb1c6`，
  因此本次提交是直接叠加在远端分支顶端 → **快进推送，无 `--force`**、不重写历史、不改其他赛题目录。
  本提交自身的完整 SHA 由 `git rev-parse HEAD` 或 GitHub 提交页读取（提交内容无法内联自己的哈希）。
- 提交表单信息（作者填写）：项目网站 <https://yanxi-workbench-w90bbjbmep1.qoder.zone>（任何人都可访问）；
  仓库 `https://github.com/YHR123960/oceanbase-powercontext`，分支 `2026-competition-ecosystem` + 该分支顶端 commit SHA；
  Qoder 账号 UID = 本人阿里云账号 ID（数值不写入仓库）。

### 未做 / 待办

- 真实用户试用与提效数据：未开展，因此不提交该类材料，也不在网站上看板任何此类数字。
- Qoder 账号 UID 口径由作者最终确定（见 README 第 10 节与 `coordination/REPLY_002.md` 第 10 节），
  调查到此结束；数值仅由作者在测试平台表单填写，公开仓库不记录。
