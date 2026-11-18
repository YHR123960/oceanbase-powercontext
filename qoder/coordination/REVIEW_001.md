# Codex 阶段检查 001（请Qoder修复，协调者不代写业务）

P2的真实PC验证结果已读取，12项通过；技术方向符合题面。
发现两项清洁环境复现问题，后续整理时请修复并实际验证：
1. requirements.powercontext.lock 第72行是 file:///mnt/d/seekdb_competition/qoder_2026/... 的开发机绝对wheel路径。须改为可在任意检出目录安装的相对vendor引用（其余依赖保留准确版本）。
2. scripts/setup_pc_env.sh 的注释给出 --python 参数，但尚未解析命令行参数。必须支持文档中的参数或统一改用明确的PYTHON_BIN环境变量；不能依赖已有minimax解释器作为干净环境唯一来源。
请不要增加不必要的功能。优先做完完整笔记→检索→关联待办→重启恢复，再建Qoder Sites项目网站。

新增界面检查（Codex读取真实截图后发现，请Qoder核对修复）：
3. evidence/screenshots/01_workbench_list.png 中当前为“在读”，但进度时间线最后一条显示“已掌握”，同秒更新顺序疑似反转。store.load 的progress按(at, seq)排序，而新progress事件seq总为1；请以正确的事件顺序/微秒时间/笔记修订号处理同秒连续更新，并加有意义的回归验证。
4. 演示笔记含“按同学反馈”等示例措辞。请在README与展示网站明确说明初始笔记/进度为构造的验证样例，不把这些文字作为真实用户反馈或提效数据。
独立测试：Codex已执行现有34项，全部通过、无跳过，结果见evidence/codex_independent_tests.json。源码和修复仍由Qoder承担。
`n范围澄清：Python >=3.11可作为README明确的环境前置条件，支持 --python 指向用户自行安装的解释器即可；无需开发Python下载器，也无需反复探测旧版GitHub发布URL。已有完整Python3.12安装与uv工具可只读使用，但交付应不依赖固定minimax路径。请优先修复现有代码/文档中的可复现问题和时间线，然后完成Sites。
