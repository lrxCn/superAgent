# 21 - Configurable Guardrails

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：allowlist、话题 block、次数上限需跨 ReAct/Plan 一致。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对任务 **20** 已完成。
3. 只实现本任务范围；跑 Agent 验收。
4. 用户要求 commit 时再提交。

## 依赖

09、14、20。

## 背景

G6：无可配置 Guardrails；违规不可观测。

## 目标

- 工具 allowlist、话题 block、`max_tool_calls_per_run`。
- 违规 → `runtime_events`（`event=security`）；ReAct / Plan 拦截。

## 范围

| Area | Change |
|------|--------|
| `src/agent/guardrails.py`（新建）或 `config.py` | 配置与校验 |
| `src/agent/nodes/react.py`, `planner.py`, `router.py` | 接入点 |
| `tests/unit_tests/` | 违规拦截 + 事件 |

## 验证方案

```bash
uv run pytest tests/unit_tests -q -k guardrail
uv run ruff check src tests
```

## Agent 验收

```bash
uv run pytest tests/integration_tests -q -k guardrail
# 或跑一条 graph integration 断言 security event
```

## 非范围

- 生产 MCP 多 server 鉴权细节

## 完成标准

- [ ] 违规可观测且调用被拦，档位：**本地可用**
- [ ] progress 21 更新

## 进度更新

`docs/progress.md` **21** → 验收后 `✅`。
