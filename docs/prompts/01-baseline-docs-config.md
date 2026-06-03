# 01 - Baseline Docs And Config Hygiene

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：这是文档与配置基线任务，需要核对仓库事实、环境变量、模板残留和后续任务入口，但不应改运行逻辑。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；本任务无依赖。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

无。

## 背景

当前仓库由 LangGraph Python 模板初始化，已有 PRD 和规划文档。第一步要把项目元数据、`.env_example`、README 和基础忽略规则整理成 SuperAgent 的稳定基线，避免后续任务在模板残留上开发。

## 目标

- 建立 SuperAgent 的文档、配置和项目元数据基线，不改变运行行为。

## 范围

| Area | Change |
|------|--------|
| `README.md` | 保持当前事实、文档顺序、目标架构和开发命令准确 |
| `pyproject.toml` | 将模板名称/描述/作者等元数据调整为 SuperAgent；补齐后续任务需要的依赖占位或 dev 依赖 |
| `.env_example` / `.env.example` | 去除真实值，只保留安全默认值；同步 PRD 中第一阶段配置 |
| `.gitignore` | 确认 `.env`、缓存、构建产物不提交 |
| `docs/progress.md` | 完成后更新任务 01 状态 |

## 实施步骤

1. 检查 `README.md`、`pyproject.toml`、`.env_example`、`.env.example`、`.gitignore` 与 PRD 是否一致。
2. 保留 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME` 等 commonAgent 迁移命名；不要写入真实 key。
3. 如果同时存在 `.env_example` 和 `.env.example`，明确保留策略：优先维护仓库当前使用的一份，并在 README 写清楚；如需要保留两份，内容必须一致且不含密钥。
4. 将 LangGraph 模板 README 中与 SuperAgent 无关的营销/示例说明清理掉。
5. 不修改 `src/agent/graph.py` 的行为。

## 验证方案

```bash
git check-ignore -v .env
uv sync --dev
uv run pytest
uv run ruff check .
```

如果依赖暂时不可用，至少运行：

```bash
git check-ignore -v .env
uv run python -m compileall src tests
```

## 非范围

- 不实现 State schema。
- 不接入硅基流动、PostgreSQL、Graphiti 或 MCP。
- 不修改 LangGraph 图行为。

## 完成标准

- [ ] README、项目元数据、环境变量样例与 PRD 一致。
- [ ] `.env` 被 git ignore。
- [ ] 没有真实密钥进入 tracked 文件。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 01 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`docs: establish superagent baseline`。

## 进度更新

`docs/progress.md` **01** -> implementation complete 后改为 `✅`.

