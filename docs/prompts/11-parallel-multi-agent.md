# 11 - Parallel Multi-Agent Orchestrator

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：该任务实现并行 Worker 编排、超时、局部失败和聚合，涉及并发状态一致性。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

03、07、10。

## 背景

第一阶段 Multi-Agent 必须支持并行 Worker 编排。默认 `WORKER_MAX_CONCURRENCY=4`、`WORKER_TIMEOUT_SECONDS=120`；超时或异常 Worker 标为 `failed`，聚合输出 partial。

## 目标

- 实现 researcher/coder/reviewer/memory_manager Worker 契约、并行调度和结果聚合。

## 范围

| Area | Change |
|------|--------|
| `src/agent/workers/` | Worker 协议、mock workers、角色实现骨架 |
| `src/agent/nodes/orchestrator.py` | Worker 选择、并行执行、超时、结果聚合 |
| `src/agent/graph.py` | multi-agent path 接入 |
| `tests/unit_tests/` | 并发、超时、失败、partial 聚合 |

## 实施步骤

1. 定义 Worker 输入输出 schema，包含 role、status、result、error、confidence。
2. 用 `asyncio` 或 LangGraph 兼容方式实现并行执行。
3. 不等待超过 `WORKER_TIMEOUT_SECONDS` 的结果。
4. 聚合状态区分 completed、partial、failed、skipped。
5. Worker 实现先使用 mock/fake LLM 行为，避免真实复杂 Agent 一次性落地。
6. 路由和 plan 步骤可以选择 multi-agent path，但不要改 planner 的核心契约。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

## 非范围

- 不实现生产级 researcher/coder/reviewer 智能。
- 不接入真实代码编辑工具。
- 不实现 memory write 策略。

## 完成标准

- [ ] 多 Worker 可并行执行。
- [ ] 超时和异常 Worker 标为 failed。
- [ ] 聚合输出 partial/completed 状态。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 11 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add parallel multi agent orchestrator`。

## 进度更新

`docs/progress.md` **11** -> implementation complete 后改为 `✅`.

