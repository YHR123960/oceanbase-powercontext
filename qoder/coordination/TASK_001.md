# Qoder 主开发任务 001

用户已授权：Codex协调验收，Qoder承担主要编码、调试、测试和Qoder Sites公开项目网站发布。不要把Codex当主要开发者；不调用其他AI代写业务。
工作区：D:/seekdb_competition/qoder_2026；分支competition/qoder-productivity，从私有比赛仓库2026-competition-ecosystem当前71fb1c6创建。全部产物只放qoder/。其他目录不能修改。先读OFFICIAL_REQUIREMENTS.md核对。Codex不编写业务代码。

## 建议功能，可由你提出合理精简
做“研习工作台”：针对课程笔记/科研阅读后的资料散乱、待办遗忘，提供本地可运行Web应用，支持资料/笔记录入、关键词和标签查找、关联待办、进度更新、刷新/服务重启后保持数据，并明确展示来源和持久化机制。可选择使用PowerContext作为真实持久层：HTTP显式Atomic Memory，不需要任何付费模型。
前后端均由Qoder编写；选择你能顺利运行与测试的最小技术栈。不能只有静态演示页面、不能用普通JSON冒充PowerContext，也不能只做连接检查。

## 可用基础设施（只读复用，不改旧项目）
WSL Ubuntu-22.04，用户yhr。
真实PowerContext官方commit437aa063264be8081fc9d032c7dde7df7995f694的服务已在独立Python3.12环境安装：
/home/yhr/seekdb_competition/minimax_sdd_2026/minimax/.runtime/pc-venv/bin/powercontext
此程序可只读复用，但不能依赖它作为唯一交付，须给自己的安装/依赖锁文件或拷贝官方wheel与许可证到qoder/vendor。
已构建官方wheel和许可证：D:/seekdb_competition/minimax_sdd_2026_backup/minimax/vendor/ （可以只读复制；不能修改minimax）。
启动新PowerContext服务应选择新目录qoder/.runtime/powercontext、新端口2893，POWERCONTEXT_HOME需WSL绝对Linux路径，HTTP_HOST127.0.0.1，HTTP_PORT2893，ACCESS_MODEdisabled，DATABASE_KINDsqlite。不配置模型、不读取任何api.env、token或账户秘密。
真实接口：POST /v1/scopes 创建隔离scope(title,summary,idempotency_key)，POST /v1/memory/remember(scope_id,kind,text)，POST /v1/atomic-memory/list(scope_id,kind,states:[active],limit:100)。应处理分页/合理限额与错误，避免冒充成功。完整官方API参考 D:/seekdb_competition/minimax_powercontext_reference/openapi/powercontext.yaml（只读）。
可选seekdb现有只读程序可用2889端口，但必须新建qoder_*库，不能碰minimax_*；只需一种指定技术，不必全用。

## 阶段安排与证据
1. 先读取任务文件，回复确认，并写coordination/REPLY_001.md：功能范围、技术栈、预计各阶段、已发现阻塞。然后连续开始实现，不等待逐步许可。
2. 编写主要代码、实际安装依赖、运行服务和有意义的测试。每阶段更新PROGRESS.md、保存实际命令/退出码/版本及测试输出到evidence/。记录真实PC写入、读取、重启和复用，保存初始数据与验证样例；不要虚构用户数或提效数据。
3. 在Qoder中使用Sites生成并发布“任何人可访问”的项目网站。网站可作为项目展示/评审入口（官方允许），必须含简介、痛点、功能、真实截图或视频、仓库链接、运行体验说明。若网站只是展示入口，清晰标注本地完整功能，不把静态数据称为线上实时PowerContext。
4. 整理README、示例、开发记录与评分对照；保存站点URL与Qoder UID（公开比赛核验用途）。UID可从你的账户界面确认，不能编造。

## 安全与协作
不触碰任何其他赛题、其他正在运行工作区、认证文件和系统配置。禁止force push/reset --hard/clean。此次先不push，由Codex统一检查合并与推送。不得代替用户登录、验证码、付费，遇到这些情况停止并写明阻塞。用户已授权正常开发与公开发布，不需要每步询问，但平台强制确认须交由用户。不要进行任何订阅购买。
每阶段保留你的实际回复和代码变更。请主动写阶段回执到coordination/，便于Codex读取。
