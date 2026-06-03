# AGENTS

- 永远使用中文回复用户，除非用户明确要求使用其它语言。
- Python 项目默认使用 `uv` 作为 Python 版本、虚拟环境和依赖管理工具。
- Node.js 版本管理默认使用 `n`。
- Docker / 容器运行环境默认使用 OrbStack。
- 开始实现任务前先读 `README.md`、`docs/progress.md`、对应 `docs/prompts/*.md` 和相关 PRD。
- 执行 `docs/prompts/` 任务卡时，先检查任务卡里的建议模型和 reasoning；不一致时先提醒用户，除非用户明确要求继续。
- 每张任务卡只做自己的范围，不顺手实现相邻任务。
- 测试通过并更新 `docs/progress.md` 后自动创建 git commit；不要自动 push，除非用户明确要求。
- 不提交 `.env`、真实密钥、缓存、构建产物或无关用户改动。
