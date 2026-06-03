# 23 - Tenant IDs And LangSmith Studio

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：`user_id` / `thread_id` / Graphiti `group_id` 贯通 checkpoint 与长期记忆，需与 LangGraph configurable 契约一致。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对任务 **18** 已完成。
3. 只实现本任务范围；跑 Agent 验收。
4. **不新建 Web UI**；**不新建** `docs/*runbook*.md` 类一次性文档。
5. 用户要求 commit 时再提交。

## 依赖

18；推荐 16。

## 背景

G8：贯通租户 ID，用 **LangGraph Studio**（`langgraph dev`）+ **LangSmith** 调试。Studio 操作随 LangGraph 版本会变，不值得单独维护一份易过时的 runbook 文件。

## 目标

- Runtime：`user_id` → Graphiti `group_id`；`thread_id` → checkpoint configurable。
- **README** 增加一小节「Studio / LangSmith 调试」（只写稳定契约：要传哪些字段、tracing 环境变量），不写逐步截图教程。
- **任务交付时**在对话里说明当前版本 Studio 里具体点哪里、填什么（一次性口头/handoff，不另存 md）。
- Agent 验收用 **pytest + curl/API**，不靠 UI。

## 范围

| Area | Change |
|------|--------|
| `src/agent/` | `user_id`、`thread_id`、`group_id` 贯通 |
| `src/agent/state.py` / `config.py` | 契约与默认值 |
| `README.md` | 简短「Studio / LangSmith」小节（字段契约 + env，非教程） |
| `tests/` | unit + integration（两 `group_id` 不串） |

## 实施步骤

1. 定义 `user_id` / `thread_id` 入口（与 LangGraph `configurable` 一致）。
2. Graphiti 读写带 `group_id`（默认由 `user_id` 推导）。
3. README 补 5–10 行：无内置 UI；`langgraph dev` + `LANGCHAIN_*`；invoke 须带 `thread_id` / `user_id` 字段说明。
4. 交付回复用户：本仓库 Studio 里要改的 configurable、LangSmith 看哪个 project/metadata（按当时环境写，不进新文件）。

## 验证方案

```bash
uv run pytest tests/unit_tests -q -k "memory or graphiti or tenant"
uv run ruff check src tests
```

## Agent 验收

```bash
RUN_GRAPHITI_TESTS=true uv run pytest tests/integration_tests -q -k "group or tenant or memory_loop"
# langgraph dev 运行时可用 curl 对两 thread/user 验证隔离
```

## 非范围

- 自建 UI、`docs/langsmith-studio-runbook.md` 或类似一次性文档
- OAuth、LangGraph Platform

## 完成标准

- [ ] ID 贯通，档位：**本地可用**
- [ ] README 有 Studio/LangSmith **契约**小节（非教程）
- [ ] 交付消息含 Studio 操作说明；Agent 验收通过
- [ ] progress 23 更新

## 进度更新

`docs/progress.md` **23** → 验收后 `✅`。
