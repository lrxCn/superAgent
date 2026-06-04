# 22 - LLM Evaluator

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：结构化 LLM 输出与 revise 对齐，需保留 fake client 单测。

## 新窗口执行规则

1. 执行前先压缩上下文。
2. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
3. 核对任务 12 已完成。
4. 只实现本任务范围；跑 Agent 验收。
5. 执行完自动 git commit，message 为 `22`；不要自动 push，除非用户明确要求。

## 依赖

12。

## 背景

G7：evaluator 现为规则型 `evaluate_output`。

## 目标

- evaluator 默认 LLM 结构化 PASS/FAIL、issues、suggestions。
- revise 消费 LLM 反馈；单测用 fake client。

## 范围

| Area | Change |
|------|--------|
| `src/agent/reflection.py` | LLM evaluator |
| `tests/unit_tests/test_reflection.py` | fake client 覆盖 |

## 验证方案

```bash
uv run pytest tests/unit_tests/test_reflection.py -q
uv run ruff check src tests
```

## Agent 验收

```bash
# 有 OPENAI_API_KEY：跑一条 reflection integration
uv run pytest tests/integration_tests/test_graph.py -q -k reflection
```

无 key → fake 单测全绿，Notes 标 **骨架** 并阻塞真 LLM 集成说明。

## 非范围

- Guardrails（21）

## 完成标准

- [ ] LLM evaluator 路径可切换；fake 单测绿
- [ ] progress 22 更新 + 档位 Notes

## 进度更新

`docs/progress.md` **22** → 验收后 `✅`。
