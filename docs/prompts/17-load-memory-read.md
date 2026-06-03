# 17 - Load Memory Read

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：Graphiti search + checkpoint 摘要 + 失败降级需与 state 契约一致。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对任务 **16** 已完成（Graphiti 本地可起；若阻塞可用 mock 完成单测，集成测标阻塞原因）。
3. 只实现本任务范围。
4. 跑验证与 Agent 验收。
5. 用户要求 commit 时再提交。

## 依赖

16（推荐）。

## 背景

G2：`load_memory` 现为占位，不读 Graphiti。

## 目标

- 用最新 user message 作 query，调 Graphiti `search`，填入 `memory_context.long_term`。
- 可选：checkpoint 摘要进 `short_term`。
- Graphiti 不可用：写 `memory_context.errors`，图继续。

## 范围

| Area | Change |
|------|--------|
| `src/agent/graph.py` 或 `src/agent/memory/read.py`（新建） | 读取编排 |
| `src/agent/memory/graphiti.py` | 如需，search → state 映射 helper |
| `tests/unit_tests/` | mock：命中、空、错误降级 |
| `tests/integration_tests/` | Graphiti 可用时 search 非空 |

## 验证方案

```bash
uv run pytest tests/unit_tests -q -k memory
uv run ruff check src tests
uv run mypy src
```

## Agent 验收

```bash
# Graphiti 按 runbook 运行
RUN_GRAPHITI_TESTS=true uv run pytest tests/integration_tests -k load_memory -q
# 若无专用文件，补一条 integration 并在此执行
```

Graphiti 未起 → 单测必须通过；集成测标 `⏸` 并说明。

## 非范围

- 读写闭环（任务 18）
- UI

## 完成标准

- [ ] 非 mock 场景 `long_term` 有内容，档位：**本地可用**
- [ ] Agent 验收通过或集成阻塞已记录
- [ ] progress 任务 17 更新

## 进度更新

`docs/progress.md` **17** → 验收后 `✅`。
