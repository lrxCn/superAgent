# 06 - Context Budget And Compression

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：该任务实现上下文预算和压缩策略，涉及状态裁剪和测试，但不接入复杂外部服务。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

02、04、05。

## 背景

SuperAgent 需要在进入模型推理前检查上下文预算，并在超限时保留当前目标、硬约束、最近交互和高价值记忆。

## 目标

- 实现 context budget 估算、压缩结果结构和可测试的裁剪策略。

## 范围

| Area | Change |
|------|--------|
| `src/agent/context_budget.py` | token/字符估算、预算检查、压缩策略 |
| `src/agent/graph.py` | 接入 `context_budget_check` / `compress_memory` 节点或等价骨架 |
| `tests/unit_tests/` | 覆盖正常、超限、当前目标保护、记忆裁剪 |

## 实施步骤

1. 先用字符或近似 token 估算实现，不引入重型 tokenizer，除非项目已有合适依赖。
2. 明确 `context_budget` state 字段：limit、estimated、compressed、summary、dropped counts。
3. 保留当前用户目标、系统硬约束、最近消息和高优先级记忆。
4. 压缩逻辑必须 deterministic，方便单元测试。
5. 将压缩结果写入 state，不直接调用 LLM 摘要；LLM 摘要可作为后续增强。

## 验证方案

```bash
uv run pytest tests/unit_tests
uv run ruff check src tests
uv run mypy src
```

如果依赖暂时不可用：

```bash
uv run python -m compileall src tests
```

## 非范围

- 不实现 LLM 摘要。
- 不实现 router 或模型调用。
- 不写入长期记忆。

## 完成标准

- [ ] 上下文预算字段写入 state。
- [ ] 超限时 deterministic 压缩。
- [ ] 当前目标和硬约束被保护。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 06 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add context budget compression`。

## 进度更新

`docs/progress.md` **06** -> implementation complete 后改为 `✅`.

