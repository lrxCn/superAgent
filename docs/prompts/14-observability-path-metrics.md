# 14 - Observability And Path Metrics

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：该任务补齐跨路径观测和测试，涉及多个已实现模块但主要是 instrumentation 和契约冻结。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

07、09、10、11、12、13。

## 背景

SuperAgent 的控制面必须可观察：输入、记忆、预算、路由、MCP、计划、并行 Worker、reflection、fallback、memory write 都应留下结构化事件或 path metrics。

## 目标

- 建立统一 path metrics / runtime events，并补齐跨路径契约测试。

## 范围

| Area | Change |
|------|--------|
| `src/agent/observability.py` | 事件 schema、path metrics、safe summaries |
| Existing nodes | 写入关键事件，不泄漏密钥和长文本 |
| `tests/unit_tests/` | 事件字段、敏感过滤、路径指标 |
| `tests/integration_tests/` | direct/tool/plan/multi-agent/fallback 路径 smoke |

## 实施步骤

1. 定义事件字段：event、path、node、status、duration_ms、summary、error_type。
2. 工具输入输出只记录摘要，不记录完整敏感数据。
3. LangSmith tracing 可通过环境变量开启，但测试不依赖 LangSmith。
4. 统一记录 fallback reason 和 memory write result。
5. 增加 characterization tests，冻结关键路径的最小事件序列。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

## 非范围

- 不接入外部 dashboard。
- 不实现复杂评测指标。
- 不改变业务路径决策。

## 完成标准

- [ ] 关键路径有结构化事件。
- [ ] 事件不泄漏密钥。
- [ ] direct/tool/plan/multi-agent/fallback 至少有 smoke 覆盖。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 14 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add runtime observability`。

## 进度更新

`docs/progress.md` **14** -> implementation complete 后改为 `✅`.

