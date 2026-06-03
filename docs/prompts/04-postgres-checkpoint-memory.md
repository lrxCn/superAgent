# 04 - PostgreSQL Checkpoint Memory

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：该任务接入 LangGraph 持久化 checkpointer，涉及依赖、初始化、降级和图编译契约。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

02。

## 背景

短期记忆使用 LangGraph checkpoint + PostgreSQL。实现应采用 `langgraph-checkpoint-postgres`，通过 `AsyncPostgresSaver.from_conn_string(DATABASE_URL)` 接入，并在首次启动或 `CHECKPOINT_SETUP=true` 时调用 `setup()`。

## 目标

- 为 graph 编译提供可选 PostgreSQL checkpointer，并保留测试用内存/mock fallback。

## 范围

| Area | Change |
|------|--------|
| `pyproject.toml` | 增加 `langgraph-checkpoint-postgres` 和 `psycopg[binary,pool]` |
| `src/agent/memory/checkpoint.py` | 封装 checkpointer 创建、setup、fallback |
| `src/agent/graph.py` | 支持带 checkpointer 编译或暴露 builder/factory |
| `.env_example` / `.env.example` | 同步 `DATABASE_URL`、`CHECKPOINT_SETUP` |
| `tests/unit_tests/` | mock `AsyncPostgresSaver`，覆盖 setup 开关和缺失数据库降级 |

## 实施步骤

1. 增加依赖并运行 `uv sync --dev`。
2. 实现 checkpointer factory；不要在 import 时连接数据库。
3. 只在运行入口或显式 factory 调用时创建连接。
4. 测试中 mock PostgresSaver，不要求本地 PostgreSQL。
5. 保证 `langgraph dev` 仍能加载 graph。

## 验证方案

```bash
uv sync --dev
uv run pytest tests/unit_tests
uv run ruff check src tests
uv run mypy src
```

如果没有 PostgreSQL，本任务仍应通过 mock 测试。可选真实验证：

```bash
uv run pytest tests/integration_tests -m postgres
```

## 非范围

- 不实现长期 Graphiti。
- 不实现 memory write policy。
- 不要求手写 SQL migration，除非库版本验证必须。

## 完成标准

- [ ] Checkpointer factory 不在 import 时连接数据库。
- [ ] `CHECKPOINT_SETUP=true` 时会调用 `setup()`。
- [ ] 无 PostgreSQL 时 mock/unit 测试可通过。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 04 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add postgres checkpoint memory`。

## 进度更新

`docs/progress.md` **04** -> implementation complete 后改为 `✅`.

