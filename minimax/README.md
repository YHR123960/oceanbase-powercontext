# MiniMax × OceanBase SDD 上下文管理

作品基于官方 2026-competition-ecosystem 分支；代码与材料全部在 minimax/。只在本地提交，未推送或触发官方评测。
验证任务：商品列表增加可选 status 筛选，保留排序、分页和返回格式。

本地六项验收全部PASS；独立干净复现退出码0。汇总见 evidence/acceptance.json，实际执行记录见 evidence/reproduction.json。

## 干净环境一键复现（不需要 MiniMax Key，不发生付费调用）

Linux/WSL2，Python 3.10（应用和 seekdb）、Python 3.12（官方 PowerContext）、Git、网络访问 PyPI。
可用其他兼容解释器，但本作品固定版本在 Ubuntu 22.04 / Python 3.10.12 + 3.12.16 验证。

```bash
cd <checkout>/minimax
# uv 安装在作品自身目录，不改其他比赛项目。
python3 -m pip install --target .runtime/tools uv==0.13.9
# 若系统没有 Python 3.12，可安装隔离解释器：
UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python" .runtime/tools/bin/uv python install 3.12.16 --no-bin
# Python 下载受限时，可加 UV_PYTHON_INSTALL_MIRROR=https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone
python3 scripts/reproduce.py --uv .runtime/tools/bin/uv \
  --python312 .runtime/python/cpython-3.12.16-linux-x86_64-gnu/bin/python3.12
```

reproduce.py 从当前提交克隆新检出目录，安装两个全新虚拟环境，启动全新 seekdb 实例（2890）和 PowerContext 服务（2891），执行全部六项检查。日志写 evidence/reproduction-*.log、events.jsonl、acceptance.json、reproduction.json。检查失败返回非零。
先提交代码再运行复现，未提交的改动不会进入新检出。需端口2890/2891空闲；已有业务实例不会被停止或删除。
PowerContext 官方源码提交 437aa063264be8081fc9d032c7dde7df7995f694 已构建为未修改的上游 wheel 随作品交付；第三方依赖通过锁文件安装。vendor 包含来源和许可证。无须依赖本机额外源码仓库。

## 日常 CLI 演示

```bash
.runtime/tools/bin/uv venv --python python3 .venv
.runtime/tools/bin/uv pip install --python .venv/bin/python -r requirements.lock
export PYTHONPATH=src SDD_DB_PORT=2889
# 终端一：新建本项目 .runtime/seekdb，Ctrl-C 正常停止。
.venv/bin/python scripts/seekdb_server.py
# 终端二，同样设置 PYTHONPATH 和 SDD_DB_PORT：
.venv/bin/python -m sdd init
.venv/bin/python -m sdd ingest --path specs/status.md --kind spec
.venv/bin/python -m sdd ingest --path sample_project/catalog.py --kind code
.venv/bin/python -m sdd ingest --path tests/test_target.py --kind target
.venv/bin/python -m sdd ingest --path tests/test_regression.py --kind regression
.venv/bin/python -m sdd context
.venv/bin/python -m sdd verify
```

输出 JSON，测试失败透传 pytest 退出码，缺失配置返回清晰错误与非零状态。
可配置 SDD_DB_HOST/PORT/USER/PASSWORD、SDD_DATABASE。仅允许 minimax_sdd_* 数据库名；SQL连接检查引擎身份，拒绝普通 MySQL。
重置不删库：为 SDD_DATABASE 设置新的 minimax_sdd_* 名称；规格变化后重新 ingest 同一路径，旧摘要失效。不要导入 .env 或其他密钥文件。

## MiniMax 真实开发记录与再次调用

真实使用 MiniMax-M3.1-Flash，普通按量计费 API，POST https://api.minimax.cn/v1/chat/completions。
已完成一次连通性验证、一次业务源码生成，无自动重试。evidence/minimax-summary.json 记录请求ID与usage，events.jsonl 保留实际上下文和返回源码，applied.diff 与前后快照可核对。
API成功说明当前额度可调用模型；该接口不能证明15元赠送余额的具体扣减顺序或剩余金额。

仅在需要新的模型修改时执行（会消耗额度；验收不执行）：

```bash
.venv/bin/python -m sdd generate --env-file <private-path>/api.env
```

凭据文件权限须600，内容为 MINIMAX_API_KEY=真实密钥；可选 MINIMAX_ENDPOINT、MINIMAX_MODEL。默认采用上述已验证官方接口和模型。不执行文件内容，仅解析白名单赋值；不打印密钥，不写入请求日志。文件应在仓库外。
模型只能替换 sample_project/catalog.py；固定测试不变。应用前做Python语法校验，应用后运行pytest。模型代码按本机普通代码执行，仅在可信开发环境使用。

## PowerContext 状态复用

使用真实 PowerContext 官方服务及其 SQLite 持久化后端。此 SQLite 仅存 PowerContext 自身状态，工程资料实际存 seekdb。
POST /v1/memory/remember 写入 task_id、描述、已完成/待办、验证结果与更新时间；POST /v1/atomic-memory/list 按任务kind读取。
验收从全新目录/空Scope开始，用子进程 state-save 保存，正常退出 CLI 与服务，重启同一服务目录，再运行 context --resume。
恢复结果把 pending_steps 映射为 next_action=package-evidence、generation_needed=false，避免重复完成的生成步骤。

单独使用时，设置 POWERCONTEXT_URL、POWERCONTEXT_SCOPE，服务需要鉴权则另设 POWERCONTEXT_TOKEN；state-save --path <state.json>、state-load、context --resume 均可调用。自动验收已管理服务、Scope和配置，不需手工准备隐藏状态。

## 样例与证据

必要来源：specs/status.md、sample_project/catalog.py、tests/test_target.py、tests/test_regression.py。
输入数据id为3(done)、1(open)、2(open)；默认按id排序，每页2项。允许open/done；无status保留原行为，非法值抛ValueError，先筛选再分页，total为筛选后数量。
固定目标6项：合法状态、筛选后total、分页前筛选、三种非法输入。回归3项：默认结果、原分页、数据不被修改。
修改前6失败是业务断言失败；修改后6通过，原回归3通过。验收还在临时样例中回放修改前源码并运行相同目标测试，确认6项真实行为失败，之后保留提交源码不变。
规格V1/V2演示由验收脚本自动完成，数据库查询证明只有新版本active；结束后还原当前规格并重新导入，使磁盘与数据库一致。

关键文件：evidence/events.jsonl（带时间、执行命令、退出码、Git版本、SQL/结果、测试哈希）、before_catalog.py.txt、after_catalog.py.txt、applied.diff、powercontext-*.log、acceptance.json、reproduction.json。
运行原始日志可能包含本次执行的绝对路径，仅用于定位证据；程序与复现步骤不依赖这些路径。

## 限制与提交

采用精确任务标签选取资料，暂不做语义向量检索；PowerContext按任务kind最多100条快照，超限明确报错。
服务仅用于本地演示；需要网络连接安装锁定依赖，Python与Linux原生轮子兼容性须符合要求。
验收PASS是本地复现结果，不代表已获得官方分数。私有比赛仓库地址尚未确认，不得向官方仓库或此前seekdb赛题仓库推送。


发布准备：用户已指定 https://github.com/YHR123960/oceanbase-powercontext 。
提交分支 competition/minimax-sdd-submit，以该仓库当前2026-competition-ecosystem提交71fb1c6b9922e599399d2df993ca5d3923182ce8为父历史，导入原交付89a9ffce18d0affd948bec1c9ae6775bf404b5ed的minimax目录。
其他赛题目录保持远端原样。当前交付SHA以本分支git rev-parse HEAD为准；早期报告中的“仓库未确认/未推送”描述仅代表开发阶段。
