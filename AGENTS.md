# AGENTS

- 永远使用中文回复用户，除非用户明确要求使用其它语言。
- Python 项目默认使用 `uv` 作为 Python 版本、虚拟环境和依赖管理工具。
- Node.js 版本管理默认使用 `n`。
- Docker / 容器运行环境默认使用 OrbStack。
- 开始实现任务前先读 `README.md`、`docs/progress.md`、对应 `docs/prompts/*.md` 和相关 PRD（增量 PRD 优先于历史 PRD）。
- 执行 `docs/prompts/` 任务卡时，先检查任务卡里的建议模型和 reasoning；不一致时先提醒用户，除非用户明确要求继续。
- 每张任务卡只做自己的范围，不顺手实现 adjacent 任务。
- **Agent 验收**：实现后必须亲自执行任务卡里的 `## Agent 验收` shell 命令（起 Docker、curl、真依赖 pytest、E2E 等）；验收不过标 `⏸ 阻塞`，不得用 mock-only pytest 标 `✅`，除非任务卡明确 skeleton-only。
- **完成档位**：progress 标 `✅` 时在 Notes 写 `骨架` / `本地可用` / `生产`；README 不得把 mock/stub 写成 Implemented。
- 规划文档（PRD、prompts 队列、`docs/todolist.md`）**不自动 commit**，除非用户明确要求。
- 实现任务：Agent 验收通过并更新 `docs/progress.md` 后，用户要求 commit 工作流时再 git commit；不要自动 push，除非用户明确要求。
- 延期项写 `docs/todolist.md`（单文件），不要为一条 todo 单独建文件夹。
- 不提交 `.env`、真实密钥、缓存、构建产物或无关用户改动。
