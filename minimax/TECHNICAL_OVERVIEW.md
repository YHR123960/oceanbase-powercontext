# 一页技术说明

CLI → seekdb资料表 → 当前active的规格/源码/目标测试/回归测试 → MiniMax HTTP → 应用业务源码 → pytest → PowerContext显式Memory → 重启后上下文。

资料以相对路径定位，以SHA-256标识内容版本，以任务标签精确选择。同一路径重新导入时，在事务内失效旧版本、激活新版本。context要求四类真实来源齐备，规格更新后只返回有效记录。

seekdb：官方pylibseekdb 1.3.0提供独立原生SQL服务，用PyMySQL连接专用数据库，存资料全文、类别、任务、摘要及active状态。真实SELECT结果直接生成模型上下文。演示与复现使用独立实例目录、端口与数据库，旧比赛资料不受影响。

MiniMax：M3.1-Flash官方OpenAI兼容HTTP接口。以真实数据库上下文生成catalog.py替换源码；记录请求ID、时间、模型、usage、上下文、响应与diff。共一次连通性验证和一次业务生成，无无限重试。验收只复核历史响应、源码与上下文摘要，不重复付费。

PowerContext：上游commit 437aa063264be8081fc9d032c7dde7df7995f694的官方服务。利用显式Atomic Memory保存状态，SQLite由官方服务自身管理。新进程从同一持久目录读取任务，恢复已完成步骤、待办和验证结果，用于决定后续动作并跳过已完成的生成。未用自行编写JSON替代PowerContext持久化。

验证：固定目标测试修改前6项业务失败、修改后6项通过、原回归3项通过；测试摘要保持一致。全新检出、两个新虚拟环境、空seekdb与空PowerContext库验证六项要求；重启官方服务与CLI后复用真实状态。证据包含命令、退出码、Git版本和内容哈希。
