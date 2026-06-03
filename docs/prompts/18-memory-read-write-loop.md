# 18 - Memory Read Write Loop

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：跨 thread write→read 集成与 Graphiti group 契约。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对任务 **17** 已完成。
3. 只实现本任务范围；跑 Agent 验收。
4. 用户要求 commit 时再提交。

## 依赖

17。

## 背景

G3：写入长期记忆后，新 thread 的 `load_memory` 应能读到。

## 目标

- integration：graph 跑完 `memory_write` → 新 `thread_id` invoke → `long_term` 非空。

## 范围

| Area | Change |
|------|--------|
| `tests/integration_tests/` | 读写闭环用例 |
| `src/agent/` | 修复闭环缺口（若有） |

## 验证方案

```bash
uv run pytest tests/unit_tests -q
```

## Agent 验收

```bash
# Graphiti 运行中
RUN_GRAPHITI_TESTS=true uv run pytest tests/integration_tests/test_memory_loop.py -q
```

（无此文件则本任务创建并跑通。）

## 非范围

- Worker、MCP、UI

## 完成标准

- [ ] 闭环 integration 绿，档位：**本地可用**
- [ ] progress 18 更新

## 进度更新

`docs/progress.md` **18** → 验收后 `✅`。
