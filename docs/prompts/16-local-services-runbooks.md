# 16 - Local Services Runbooks

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：OrbStack compose、Postgres、`langgraph dev` 挂载说明需对照现有 checkpoint/Graphiti 代码。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对 Phase 1（01–15）已完成。
3. 只实现本任务范围。
4. 跑 `验证方案` 与 `Agent 验收`；不过不标 ✅。
5. 用户要求 commit 时再提交。

## 依赖

Phase 1 完成（01–15）。

## 背景

G1：本地 Graphiti + Postgres 必须能按文档起服。Phase 1 runbook 过薄。

## 目标

- 补全 Graphiti OrbStack runbook 与 Postgres checkpoint 本地 runbook。
- `langgraph dev` 如何挂 PostgreSQL checkpointer 写清楚。

## 范围

| Area | Change |
|------|--------|
| `docs/graphiti-orbstack-runbook.md` | compose 命令、`.env`、health、排查 |
| `docs/postgres-local-runbook.md`（新建） | Docker/OrbStack Postgres、`DATABASE_URL`、`create_graph_with_checkpointer` |
| `README.md` | 链到两份 runbook |

## 实施步骤

1. Graphiti：官方 `mcp_server/docker` compose，写逐步命令与 SuperAgent 环境变量。
2. Postgres：`postgres:16` 容器、库名 `super_agent`、与 `.env_example` 对齐。
3. 说明 `langgraph dev` 默认内存 checkpointer vs Postgres 可选路径。
4. 去掉 integration 里 MCP smoke 的**无条件** skip（若仍存在）。

## 验证方案

```bash
uv run ruff check .
uv run pytest tests/unit_tests -q
```

## Agent 验收

Agent 必须亲自执行：

```bash
# Graphiti（按 runbook 起栈后）
curl -sf http://localhost:8000/health
RUN_GRAPHITI_TESTS=true uv run pytest tests/integration_tests/test_graphiti_memory.py -q

# Postgres（按 runbook 起库后）
RUN_POSTGRES_TESTS=true uv run pytest tests/integration_tests/test_postgres_checkpoint.py -q
```

环境不可用 → `⏸ 阻塞` 并写明缺什么，不得标 ✅。

## 非范围

- `load_memory` 读实现（任务 17）
- CI workflow

## 完成标准

- [ ] 两份 runbook 可跟做，档位：**本地可用**
- [ ] Agent 验收命令已执行通过（或阻塞原因已记录）
- [ ] `docs/progress.md` 任务 16 更新

## 进度更新

`docs/progress.md` **16** → Agent 验收通过后 `✅`，Notes 写 `本地可用`。
