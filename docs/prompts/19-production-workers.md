# 19 - Production Workers And Plan Agent Steps

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：四角色 LLM Worker、registry 默认切换、Plan agent 步与 orchestrator 契约。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对 Phase 1 任务 11 已完成。
3. 只实现本任务范围；跑 Agent 验收。
4. 用户要求 commit 时再提交。

## 依赖

11；推荐 16–18 已完成。

## 背景

G4：multi_agent 默认 mock；Plan `type: agent` 步 skip。

## 目标

- 四角色生产 Worker（SiliconFlow + role prompt）。
- 默认 registry 指向生产；测试可 inject mock。
- `ExecutePlanNode`：`type: agent` 调单 Worker，状态 `completed`/`failed`，非 `skipped`。

## 范围

| Area | Change |
|------|--------|
| `src/agent/workers/` | 生产 Worker 实现 |
| `src/agent/nodes/planner.py` | agent 步执行 |
| `src/agent/nodes/orchestrator.py` | 默认 registry |
| `tests/unit_tests/` | mock 单测保留 |
| `tests/integration_tests/` | 真 LLM 或 fake 一条 plan agent 路径 |

## 验证方案

```bash
uv run pytest tests/unit_tests/test_orchestrator.py tests/unit_tests/test_plan_execute.py -q
uv run ruff check src tests
```

## Agent 验收

```bash
# .env 有 OPENAI_API_KEY 时
uv run pytest tests/integration_tests -k "worker or plan_agent" -q
```

无 key → 单测必须绿；真 LLM 集成标阻塞或 skip 并记录，**不得** mock-only 标 ✅。

## 非范围

- UI
- Guardrails

## 完成标准

- [ ] 默认非 mock 文案；plan agent 非 skipped，档位：**本地可用**（有 key）或 **骨架**（仅 fake 测通且 Notes 说明）
- [ ] progress 19 更新

## 进度更新

`docs/progress.md` **19** → 验收后 `✅` + 档位 Notes。
