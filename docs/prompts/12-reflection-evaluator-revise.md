# 12 - Reflection Evaluator And Revise

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：Reflection 会影响最终输出质量、fallback 和循环控制，需要明确策略阈值和测试护栏。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

08、09、10、11。

## 背景

Reflection 部分开启：tool、plan、multi-agent、fallback 前、低置信路由、高风险关键词/类别、用户显式要求检查时开启。低置信阈值为 `route_confidence < 0.72`，最大修正轮次为 1。

## 目标

- 实现 reflection gate、evaluator、revise 和 max rounds 控制。

## 范围

| Area | Change |
|------|--------|
| `src/agent/reflection.py` | reflection gate、risk rules、evaluator schema、revise 策略 |
| `src/agent/graph.py` | reflection path 接入 |
| `tests/unit_tests/` | gate 策略、低置信、高风险、pass/fail、max rounds |

## 实施步骤

1. 定义 `EvaluationResult`：status、issues、suggestions、round、requires_revision。
2. 实现 gate：路径、置信度、fallback 前、用户显式要求、高风险关键词/类别。
3. 第一阶段 evaluator 可先规则化或 fake LLM，保证测试稳定。
4. FAIL 且未超过轮次时进入 revise；超过后进入 fallback。
5. direct low-risk path 不强制 evaluator。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

## 非范围

- 不实现复杂 LLM-as-judge prompt 库。
- 不引入在线评测平台。
- 不改变 memory write 策略。

## 完成标准

- [ ] Reflection gate 对启用/跳过给出理由。
- [ ] `route_confidence < 0.72` 会触发 reflection。
- [ ] FAIL 后最多 revise 1 轮。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 12 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add reflection evaluator`。

## 进度更新

`docs/progress.md` **12** -> implementation complete 后改为 `✅`.

