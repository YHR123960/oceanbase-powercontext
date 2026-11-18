# 时空旅店·夜班前台（Dify × PowerContext）

> Just for Fun——用 Dify 做一个好玩的智能应用。一家开在时空裂缝里的旅店，AI 店小二「阿灯」用 PowerContext 记住每一位住客：喜好、选择、发生在 TA 身上的剧情。换一个新会话再来，阿灯依然认得你，故事会接着上次讲下去。

## 一、作品创意与玩法

**玩法**：你在「住客代号」里写下自己的名字，然后和前台阿灯聊天。旅店每晚都会发生奇怪的小事件（AI 即兴创作），你的回应会影响剧情走向。更重要的是——**这家旅店会记住你**：

- 第一晚：阿灯不认识你，请你登记称呼与来意；
- 之后的每一轮互动：阿灯会把你的关键信息（喜好、选择、关键事件）写入旅店档案；
- **任意新会话**：用同一个住客代号再来，阿灯会自然地"认出"你，并引用上次发生的事延续剧情——这是本作品的核心记忆玩法。

**体验方式**：在 Dify 中打开该 Chatflow 应用（或通过 Dify API 调用），填入住客代号后直接对话即可，无需其他操作。

## 二、技术分工

| 技术 | 在本作品中的作用 |
| --- | --- |
| **Dify（必选）** | 承担全部流程编排：接收用户输入 → HTTP 节点查询记忆 → 代码节点整理档案 → LLM 生成前台剧情回复 → LLM 提炼本轮记忆 → HTTP 节点写回档案 → 输出回答。共 7 个节点、6 条边。 |
| **PowerContext（单选项）** | 作为跨会话记忆存储。使用其两个 HTTP API：`POST /v1/memory/search`（接待前检索该住客的历史记录）与 `POST /v1/memory/remember`（互动后写入一条 `guest_story` 记忆）。每个住客代号对应一个 PowerContext scope（`scope_id = 住客代号`），实现"换个会话依然被记得"。 |

按赛题规则，选择 PowerContext 的作品不要求同时使用 seekdb，本作品未使用 seekdb。

## 三、运行环境与依赖

| 项 | 要求 |
| --- | --- |
| Dify | 1.x（DSL 由 Chatflow 导出格式编写，适用 Dify ≥ 1.0；老版本如导入失败，按节点说明手动重建，节点参数已完整写在 DSL 中） |
| PowerContext | 仓库 `oceanbase/powercontext`（或本队私有仓库同路径 `src/powercontext`），以 HTTP Server 方式启动，默认端口 `8000` |
| 模型服务 | 任意 Chat 模型（DSL 默认写的是 `langgenius/openai/openai / gpt-4o-mini`，导入后请改为你环境里已配置的模型，共 2 个 LLM 节点） |
| 插件 | 无第三方插件依赖，仅用 Dify 内置的 HTTP Request / Code / LLM / Answer 节点 |
| Embedding / Rerank | 不需要（PowerContext 自身负责记忆检索，本应用未使用 Dify 知识库） |

## 四、部署步骤（从零到可玩）

1. **启动 PowerContext HTTP 服务**
   ```bash
   # 获取代码后进入服务目录（占位示例，按仓库 README 的实际启动命令执行）
   git clone https://github.com/oceanbase/powercontext.git
   cd powercontext
   # 安装依赖并启动 HTTP Server（默认监听 8000 端口）
   # 具体命令以仓库 docs/README 为准，例如：
   # uvicorn powercontext.http.app:app --host 0.0.0.0 --port 8000
   ```
   启动后用 `curl http://localhost:8000/health/live` 确认返回正常。

2. **导入 DSL**
   - Dify 控制台 → 工作室 → 导入 DSL 文件 → 选择 `dsl/time-inn-chatflow.yml`；
   - 导入后进入编排页面，确认 7 个节点连线完整。

3. **修改 3 处配置（全部为占位值，不含真实密钥）**
   - **环境变量**：`POWERCONTEXT_BASE_URL`（默认 `http://localhost:8000`）改为你的 PowerContext 实际地址；
   - **两个 LLM 节点**（"前台阿灯回应"、"提炼本轮记忆"）：把模型改为你环境可用的 Chat 模型；
   - 无需配置任何 API Key 于应用内（模型密钥在 Dify 系统设置中配置，PowerContext 无鉴权密钥）。

4. **发布并体验**
   - 发布应用 → 预览/访问，在开始表单中填入住客代号（如 `keke`），开始对话。

## 五、验证样例

见 [examples.md](examples.md)。核心验证点：

1. **首轮登记**：新住客代号 → 阿灯询问称呼来意 → 回答后档案新增记忆；
2. **记忆复用（核心）**：**结束该会话，开一个全新会话**，用同一住客代号 → 阿灯应主动"认出"你并引用上次的剧情/喜好；
3. **数据核对**：`curl -X POST http://localhost:8000/v1/memory/search -H "Content-Type: application/json" -d '{"scope_id":"<住客代号>","query":"姓名 喜好 剧情","limit":10}'` 能看到对话中写入的 `guest_story` 记录，且与回答中引用的内容一致。

## 六、已知功能限制

- 记忆提炼由 LLM 输出单行文本写入 JSON 请求体，提示词已强制"不含英文双引号/换行"；若模型不遵守，`POST /v1/memory/remember` 可能返回 422，该轮记忆不会写入（不影响当轮回复）；
- PowerContext 服务未启动时，记忆查询/写入节点会重试后失败，对话可能中断——体验前请确认服务已就绪；
- 应用不校验住客代号唯一性：换一个代号即等于"一位新客人"（这本身也是玩法的一部分）。

## 七、文件清单

| 文件 | 用途 |
| --- | --- |
| `dsl/time-inn-chatflow.yml` | Dify Chatflow DSL（唯一导入文件，导入顺序无依赖） |
| `README.md` | 本运行说明 |
| `examples.md` | 验证样例、预期交互与记忆复现证据说明 |
