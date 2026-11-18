# Qoder 回执 002（REVIEW_001 第 1–4 项整改 + Sites 发布）

时间：2026-11-18 11:12（本地）　执行：Qoder（主开发）　验收：Codex
改动范围：仅 `qoder/`。**未执行 git push / commit**，等待 Codex 统一验收。

## 1. 依赖锁不再写死开发机绝对路径

- `requirements.powercontext.lock` 重新生成：**122 条**精确版本，`file:` 引用 **0 处**；
  `powercontext` 本体不进锁文件，改由 `vendor/` 的官方 wheel 安装（锁文件头部注释写明原因）。
- `scripts/replay_lock.sh` 在全新一次性 venv 中回放，日志 `evidence/p1_lock_replay.log`：

  ```text
  Python 3.12.16
  + ... -m pip install --quiet -r requirements.powercontext.lock
  + ... -m pip install --quiet '/mnt/d/.../vendor/powercontext-0.1.dev1+g437aa0632.d20261118-py3-none-any.whl[builtin,server,cli]'
  0.1.dev1+g437aa0632.d20261118
  replay OK: 122 pinned dependencies + powercontext-0.1.dev1+...-py3-none-any.whl
  SCRIPT_EXIT=0
  ```

- 你指出的 glob 问题已修：先解析 wheel 路径再整体加引号拼 extras
  （`WHEEL="$(ls "$ROOT"/vendor/powercontext-*.whl | head -1)"` → `pip install "${WHEEL}[builtin,server,cli]"`），
  上面日志第三行的单引号包裹即修正生效的直接证据；wheel 缺失时脚本以明确报错退出而不是静默不装。

## 2. `setup_pc_env.sh` 真正解析参数，且不依赖其他项目

- 现支持 `--python PATH` / `--python=PATH` / `--venv PATH` / `--venv=PATH` / `-h|--help`，未知参数退出码 2；
  同时支持 `PYTHON_BIN` 环境变量。`--help` 文本由脚本头部注释生成（不再出现 `set -euo pipefail` 之类的实现行）。
- 解释器候选只列通用位置（`python3.13/3.12/3.11/python3`、`/usr/local/bin/python3`、`/usr/bin/python3`），
  并用 `python_usable()` 强制 `(3,11) <= version < (4,0)`；**没有任何 minimax 固定路径**，也不下载 Python。
- 本次回放使用你提供的只读解释器仅为“提供一个满足版本的 Python”，交付说明里评审可用任意满足版本的解释器
  （README 第 2 节写明前置条件与 `--python` 用法）。

## 3. 同秒连续更新的进度时间线顺序

- `store.now()` 改为微秒精度 ISO 时间戳；进度记录新增并写入 `note_seq`（该次状态切换对应的笔记修订号）。
- `store.load()` 排序键改为 `(at, note_seq, seq)`：`seq` 对进度事件恒为 1，因此笔记修订号成为同秒决定性依据。
- 回归测试（均通过）：
  - `tests/test_store.py::test_same_second_updates_order_by_note_revision`
    冻结时间到同一秒，断言 `reading(r2) → mastered(r3) → reading(r4)`，并断言时间线末项状态 == 卡片当前状态；
    随后把服务端返回顺序整体反转再读一次，结果不变。
  - `tests/test_live_powercontext.py::test_same_second_status_changes_order_by_revision_on_the_server`
    对**真实 PowerContext** 写三次同秒状态切换，断言三条记录时间戳完全相同且顺序仍按修订号。
- 顺带修掉一个自查出的缺陷：`load()` 里累加器与原始记录列表同名，导致 `record_counts.note_records` 实际报告可见笔记数；
  重命名累加器后由 `tests/test_store.py::test_record_counts_separate_memories_from_visible_items` 锁住
  （1 条可见笔记 = 2 条 Atomic Memory 记录）。
- 全量测试：`PYTHONPATH=src python -m pytest -q -rA` → **37 通过 / 0 失败 / 0 跳过**
  （19 领域模型 + 9 HTTP 接口 + 9 真实 Server），证据 `evidence/p3_pytest_output.txt`、`evidence/p3_pytest_junit.xml`。

## 4. 演示数据标注为构造样例

- `scripts/seed_demo.py` 升级为 `seed:demo-v2`：每条笔记带 `构造样例` 标签、正文首行
  “（构造样例，非真实反馈）”，进度备注统一 `构造样例｜` 前缀；原先“按同学反馈把局限页拆成两页”这类
  读起来像真实反馈的措辞已不在演示数据集中，且演示时间线本身也移进了脚本（不再依赖临时文件）。
- 截图全部按新数据重拍（1600×1000，真实界面 + 真实 2893 服务）：`evidence/screenshots/01..04.png`，
  新 `evidence/screenshots/capture_manifest.json` 记录 URL、Scope、契约、命令与“截图辅助脚本只在
  `.runtime/capture/` 副本里、仓库文件 md5 未变”的说明。
- 旧库兼容：`seed_demo.py` 现在会识别“标题相同但缺 `构造样例` 标签”的旧版演示笔记，为它们追加一条新修订补上标签，
  并且**不会重复写入**。在受控 workspace 上实测：

  ```text
  旧版演示笔记 4 条已补上「构造样例」标签（追加新修订，旧记录仍可查）
  演示数据已存在（4 条），跳过写入。Scope=scp_7546eq8cmfkd8fg9g2tdg2j3ne
  ```

  按 append-only 原则，旧库中已存在的进度备注不会被改写；因此截图与演示以全新 home 为准。
  README 第 6 节写明这一点。本机默认 home（`.runtime/powercontext`）已按文档步骤全新初始化并重灌
  `seed:demo-v2`（4 条笔记 / 8 条笔记记录 / 4 条进度记录），旧 home 保留在 `.runtime/powercontext-v1-archive`。
- README 第 6 节与展示网站“演示数据是构造样例”一节均明确：这些文字不是真实同学反馈、不是提效数据，
  且不给出“节省多少小时”的数字。

## 5. Qoder Sites 公开展示网站（已发布）

- 站点：**https://yanxi-workbench-w90bbjbmep1.qoder.zone**
- 可见范围：**任何人都可访问**（`access_mode: public`，`auth_integration_status: not_required`）；
  已用 `curl` 在无登录态下验证首页 `HTTP 200`，四张截图 `HTTP 200` 且 md5 与仓库 `site/web/assets/` 一致。
- 发布过程（同一 Project/Site，未创建替代站点）：
  - 首版 action `b6881cb3-62e8-48cb-b9ea-fe30f2797dcf` → `published: true`（operation `01a1ec95-6695-…` committed）；
  - 第 4 项整改后新版 action `9a24ef5c-b47d-428b-ad76-3a1d94bbbc0b` → `published: true`
    （operation `01a1eca1-252d-…`，`readiness: publication_completed`）；
  - Project `01a1ec92-f0ff-722d-9116-662450a41778`、Site `01a1ec92-f102-7a66-a606-4d32634d32b0` 全程复用。
- 网站源码同步保存在 `qoder/site/web/`（发布用目录为本会话工作区，内容一致）。

## 6. 材料状态

- 新增 `qoder/README.md`：环境前置条件（CPython ≥ 3.11、无需凭据/模型）、从安装到启动的完整步骤、
  接口表与硬限制、验证与证据表、构造样例声明、评分维度对照、提交材料清单。
- `qoder/coordination/REPLY_002.md`（本文件）、`qoder/PROGRESS.md` 已更新到真实状态。
- 未增加任何新功能：`web/app.js` 保持原状（此前为截图临时加过的深链处理已完全回退）。

## 7. 需要你/作者处理的一件事

**Qoder 账号 UID 无法由开发会话读取**，三条路径均未开放：`qc-cli user get` 返回
「当前会话身份或能力未开放此操作」；`auth.sdkIdentity.getUserInfo` 同样未开放；
`mcp__qoder-settings__manage_app_agent({action:"get"})` 返回 `available:false`
（`reasonType:"agent.executable"`）。按「权限不足即停止并报告」的要求，我没有猜测或编造任何数字，README 第 10 节以
“待作者填写”标注。查看位置见 Qoder 官方文档《站点》一节：**设置 → 个人资料 → 编辑**中的 Qoder UID
（<https://docs.qoder.cn/qoder/sites.md>）；进一步的结论见本文件第 10 节。

其余项已按 REVIEW_001 完成并留有可复核证据，等待 Codex 独立验收；期间未 push、未改动 `qoder/` 以外目录，
未读取任何凭据文件。

## 8. 交付清洁性复查（推送前）

- **发现并修复：证据日志原本会被全局 gitignore 吞掉。** 开发机配置了
  `C:/Users/14037/git.ignore`（`core.excludesFile`），其中 `*.log` 使
  `evidence/p1_lock_replay.log` 处于忽略状态——PROGRESS 与本报告都引用它作为 P1/P8 证据，
  但 `git add qoder/` 会静默漏掉这个文件。已在 `qoder/.gitignore` 末尾加
  `!evidence/*.log`（仓库内规则优先于全局排除），实测：

  ```
  $ git check-ignore -v qoder/evidence/p1_lock_replay.log
  qoder/.gitignore:8:!evidence/*.log	qoder/evidence/p1_lock_replay.log
  $ git status --porcelain -uall qoder | grep .log
  ?? qoder/evidence/p1_lock_replay.log
  ```

- **站点内容未因此变更**：网站只引用 `site/web/assets/*.png`（截图字节一致）与
  「122 项精确版本」等仍然准确的数字，没有出现 123 项、旧 r1 说明或提效数字，
  故未为本次 README/gitignore 修订再发一版。
- `git status --porcelain` 全部改动位于 `qoder/`（62 个待提交文件），`qoder/.runtime/` 被忽略，
  无凭据文件、无 venv、无 `.pytest_cache`；**未执行 push，索引保持为空**（`git add` 仅用 `--dry-run` 验证）。
- 验证完成后的收尾：停掉截图用的临时应用（`.runtime/capture/src`，端口 2897）；
  `evidence/screenshots/capture_manifest.json` 引用的 capture 数据目录保留在磁盘上以供追溯。
  文档口径的服务仍在运行：PowerContext 127.0.0.1:2893（第 9 节重启后为 pid 9007）、应用 127.0.0.1:2894（pid 8786）。
- 全局排除规则对**未来新增的 `*.log`** 仍生效（如临时日志）；交付证据若为日志形态，
  请放在 `evidence/` 下，或改用 `.txt` 后缀，避免再次被静默忽略。

## 9. 文档/gitignore 修订后的重跑验证（2026-11-18 11:28，默认 home 与文档端口）

- `PYTHONPATH=src python -m pytest -q` → **37 passed**（19 store + 9 server API + 9 live），无失败无跳过。
  本轮改动只在 `README.md`、`PROGRESS.md`、`REPLY_002.md`、`qoder/.gitignore`，源码未变；
  存储的 `evidence/p3_pytest_output.txt` / `_junit.xml`（11:12）与本结果一致。
- `python scripts/verify_pc.py --json evidence/p2_pc_verify.json` → **12/12 PASS**，
  证据文件已刷新（`run_id=20261118-112815`、`url=http://127.0.0.1:2893`、本次 server_id
  `35a76202-1837-41d7-8a10-11bc627a0612`、contract 1.5、`checks_passed=12/12`、`pc_calls_traced=30`），
  写入使用脚本自有的幂等键 Scope `scp_231kd7myj7ax66s9chtzt3v8ck`，不进入演示 Scope。
- `python scripts/e2e_restart.py --json evidence/p5_e2e_restart.json` → **10/10 PASS**（`E2E_EXIT=0`），
  真实执行 `start_pc.sh stop`（`stopped pid=8661`）→ 连接被拒 → `start_pc.sh start` 拉起新进程，
  重启后按 kind 的记录 digest 与重启前逐项相同（`24434537c0feed4e/5`、`9e8f05b3e3b602fd/2`、`e8a088c25480ebf2/1`）、
  `qoder-yanxi-workbench:e2e` 解析回同一 Scope、15639 字节长正文 3 块逐字拼回。证据文件已刷新。
- **一处需要纠正的表述（避免误导验收）**：`server_id` 是**每次启动生成**的，不是持久身份。
  今天实测同一份数据在三次启动中分别报告 `c44f83ce…`（原始 home 首启，见 PROGRESS P2）、
  `673465cf…`（截图专用 home，见 `capture_manifest.json`）、`35a76202…`（本次重启后）。
  持久性由另外两件事证明：`scope_idempotency_key` 在重启后解析回**同一个 Scope**，
  以及重启前后**每条 Atomic Memory 的 digest 与条数一致**。
  README 第 4 节把可复用身份锚在幂等键 `qoder-yanxi-workbench:<workspace>` 上；界面“数据来源”面板显示的
  server_id 是**当前进程**的真实值，换一次启动就会变，这属预期而非异常。
- 重跑后复核界面数据未被污染：演示 Scope 仍是 4 条笔记 / 5 条待办（`note_records=8`、
  `task_records=6`、`progress_records=4`），四条笔记的时间线末项状态与卡片状态一致
  （`reading`(note_seq 3)、`mastered`(2)、无进度=`unread`、`reading`(2)），时间戳为微秒精度。

## 10. Qoder 账号 UID 与“阿里云账号 ID”能否等同（2026-11-18 核对）

作者提供：Qoder CN 网页端「个人信息」显示其阿里云账号 ID（16 位数字，数值不写入本仓库），询问赛题要求填写的
“Qoder 账号 UID”是否就是它。**核对结论：不能确认二者等同，也没有任何官方材料把二者划等号。**

依据（均为原文核对，非推测）：

1. **官方赛题文档只描述用途，不定义取值**：《Qoder》赛题页（yuque `uygu3273xzlrcmrm`）提交材料表写
   “关键开发环节的 Qoder 对话截图或录屏，并附 Qoder 账号 UID，用于核对站点归属及使用记录”，提交方式写
   “登录大赛测试平台，进入 Qoder 赛题的提交入口。填写项目网站网址、代码仓库地址和 Qoder 账号 UID”。
   全文（含 2.3 的“企业版账号无法设置公开访问，请使用个人账号发布”）没有出现“阿里云”字样，也没有说明 UID 从哪里读取。
2. **《FAQ - 大赛常见问题答疑》（yuque `gp48z4pp0q3zg9b2`）全文 0 次出现 “UID”**（已解码正文逐字统计），
   其中与 Qoder 相关的只有判题耗时、0 分情形与权益领取，未定义该字段。
3. **Qoder 官方文档给出的查看位置是产品内的 “Qoder UID”**：《站点》文档原文
   “选择**仅受邀用户可访问**时，填写对方的邮箱地址或 Qoder UID……**Qoder UID 可以在设置 → 个人资料 → 编辑中查看。**”
   即 Qoder 侧确有独立的 UID 概念与官方查看入口，而不是“阿里云账号 ID”的别称。
   （<https://docs.qoder.cn/qoder/sites.md>）
4. **两条产品线账号体系不同，混填风险真实存在**：《Qoder CN（全家桶）账号与订阅》写“个人使用的是手机号绑定的阿里云账号；
   如该手机号未注册阿里云，将在购买时自动创建对应的阿里云账号”，且“个人版……必须使用阿里云主账号登录使用”；
   阿里云《账号 ID》文档写“阿里云为每一个账号分配一个唯一的由 16 位数字组成的标识符……称之为账号 ID，也叫 Account ID 或 UID”。
   两者说明 **Qoder CN 个人账号以阿里云账号为主体**，因此作者这串 16 位数字确实是其阿里云 UID，
   但“赛题字段 = 阿里云 UID”这一步官方没有写过，属于未证实的推断。
   （<https://docs.qoder.cn/product-overview/account-and-subscription.md>、<https://help.aliyun.com/zh/sae/check-account-id>）
5. **会话内无法代查**：本会话 `account.avatarEditor`（头像/资料编辑器）`available:false`、`agent.executable:false`，
   返回说明为“仅登记，暂不开放 Agent 调用”，前置条件包含“用户手动打开 Profile 设置页”；`auth.sdkIdentity.getUserInfo`
   同样未开放。因此我无法在应用内读出“设置 → 个人资料 → 编辑”里显示的那串 UID，与作者提供的账号 ID 直接比对。

给作者的可执行判断顺序（任一即可确定，无需猜测）：

- 在 Qoder Desktop 打开 **设置 → 个人资料 → 编辑**，看该处是否显示 Qoder UID 及其数值；若与作者提供的阿里云账号 ID 一致，
  则可按此填写，若显示为另一串值，以应用内显示为准。
- 登录大赛测试平台的 Qoder 赛题提交入口，核对该字段的提示/示例文字（这是最终裁判，登录态只能由作者本人查看）。
- 仍不一致或页面无说明时，走官方答疑：ask.oceanbase.com 赛题问答区（如 Token 领取指南帖
  `https://ask.oceanbase.com/t/topic/35653137`）与页面提供的钉钉技术答疑群，问题写明“提交表单的 Qoder 账号 UID 指的是
  Qoder 个人资料中的 Qoder UID，还是阿里云账号 ID”。

交付影响：README 第 10 节据此改写为“填写位置 + 核对状态”，**未写入这串账号 ID 数值**；本节原先引用的数值也已一并去除
（`grep -rn` 确认整个 `qoder/` 目录不再出现该 16 位数字）——账号标识不应出现在公开仓库。
其余交付内容、代码与证据未因本次核对改动，站点无需重发（页面不含 UID 字段）。

**作者决定（2026-11-18，本项到此结束）**：以本人阿里云账号 ID 作为本次比赛提交的 Qoder 账号 UID，由作者本人在测试平台表单填写。
README 第 10 节据此改为“填写口径 + 来源页面”，仍不记录完整号码；后续不再调查、质疑或要求核对其他编号。

## 11. 最终交付：提交并推送（2026-11-18，作者直接指示）

作者确定 UID 口径后指示完成最终交付，第 7、8 节里“等待 Codex 验收、未 push”的状态到此结束。

- 推送前复查：62 个交付文件全部位于 `qoder/`，`qoder/` 以外 0 项改动；全目录扫描无凭据、无账号 ID 数值；
  `pytest` 37 通过（19/9/9）、`p2_pc_verify.json` 12/12、`p5_e2e_restart.json` 10/10、截图与站点资源 md5 一一对应、
  站点无登录态 200。
- 远端 `origin` = `https://github.com/YHR123960/oceanbase-powercontext`；本地 `2026-competition-ecosystem` 与
  `origin/2026-competition-ecosystem` 同为 `71fb1c6`，提交叠加在该顶端 → **快进推送、无 `--force`、不重写历史**，
  `dify/`、`gaode/`、`minimax/`、`stepfun/` 等其他赛题目录未被触及。
- 提交表单三项：站点 <https://yanxi-workbench-w90bbjbmep1.qoder.zone>；仓库分支 `2026-competition-ecosystem` + 顶端 commit SHA；
  Qoder 账号 UID 按作者决定填写其阿里云账号 ID（数值不写入公开仓库）。完整 SHA 由 `git rev-parse HEAD` 读取并在对话中回报。
