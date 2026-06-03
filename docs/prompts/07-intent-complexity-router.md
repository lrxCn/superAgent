# 07 - Intent And Complexity Router

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：路由是控制面核心，会影响 direct、tool、plan、multi-agent、fallback 和 reflection 的后续路径。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

02、03、06。

## 背景

SuperAgent 要根据任务类型、复杂度和约束选择 direct、react、planner、multi-agent 或 fallback。第一阶段可先做规则路由，并保留 LLM 路由扩展点。

## 目标

- 实现结构化 `intent_decision` 和可测试路由函数。

## 范围

| Area | Change |
|------|--------|
| `src/agent/router.py` | 路由决策 schema、规则路由、置信度、理由 |
| `src/agent/graph.py` | 接入 conditional edges 或等价路由节点 |
| `tests/unit_tests/` | 覆盖 direct/tool/plan/multi-agent/fallback/low-confidence |

## 实施步骤

1. 定义 `IntentDecision` 字段：route、reason、confidence、signals、requires_reflection。
2. 先实现规则路由：工具关键词、复杂多步骤信号、专业分工信号、输入不足、普通问答。
3. 低置信阈值固定为 `0.72`，与 PRD/README 一致。
4. 路由必须输出可观察理由，不只返回字符串。
5. 图级测试验证不同输入进入不同占位路径。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

## 非范围

- 不实现各路径的完整业务。
- 不实现 LLM router prompt。
- 不实现 reflection evaluator。

## 完成标准

- [ ] `intent_decision` 结构化写入 state。
- [ ] 至少 direct/tool/plan/multi-agent/fallback 五类路由有测试。
- [ ] 路由理由和置信度可观察。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 07 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add intent complexity router`。

## 进度更新

`docs/progress.md` **07** -> implementation complete 后改为 `✅`.

