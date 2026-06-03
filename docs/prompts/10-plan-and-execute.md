# 10 - Plan-And-Execute Path

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：计划拆分和执行会跨 LLM、工具、状态和路径控制，需要较强的架构一致性。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

03、07、09。

## 背景

复杂目标应先生成计划、校验计划、按步骤执行，并记录中间观察结果。步骤可以是普通 LLM、工具或后续专业 Agent。

## 目标

- 实现 Plan schema、plan_validate、execute_plan 和最小步骤执行循环。

## 范围

| Area | Change |
|------|--------|
| `src/agent/planning.py` | Plan/Task schema、校验、状态更新 |
| `src/agent/nodes/planner.py` | planner、plan_validate、execute_plan、step_observe |
| `src/agent/graph.py` | planner path 接入 |
| `tests/unit_tests/` | 计划合法性、依赖、失败、工具步骤 |

## 实施步骤

1. 定义 plan 字段：id、title、type、dependencies、acceptance_criteria、status、result。
2. 计划生成可先用 deterministic planner 或 fake LLM，确保测试稳定。
3. `PLAN_MAX_STEPS=12`。
4. 计划校验失败进入 fallback 或 revise plan，第一阶段可先 fallback。
5. 工具步骤复用任务 09 的 MCP/ReAct observation 能力。
6. 专业 Agent 步骤先标记为待 multi-agent 任务接入，不实现并行。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

## 非范围

- 不实现并行 multi-agent。
- 不实现 reflection evaluator。
- 不实现长期 memory write。

## 完成标准

- [ ] 复杂任务可生成结构化 plan。
- [ ] plan_validate 能拒绝无依赖闭环/无验收标准的计划。
- [ ] execute_plan 可执行 LLM/mock 和工具/mock 步骤。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 10 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add plan execute path`。

## 进度更新

`docs/progress.md` **10** -> implementation complete 后改为 `✅`.

