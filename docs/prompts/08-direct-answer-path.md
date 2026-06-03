# 08 - Direct Answer Path

## 建议执行模型

- 模型：GPT-5
- Reasoning：medium
- 原因：该任务实现最小可用直答路径，需要正确使用 LLM adapter 和路由结果，但范围较窄。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

03、07。

## 背景

简单低风险请求应直接回答，不进入工具、计划或多 Agent 路径。Direct answer 是第一条用户可感知路径。

## 目标

- 实现可测试 direct answer 节点，使用 LLM adapter 或 fake LLM，并写入 `final_answer`。

## 范围

| Area | Change |
|------|--------|
| `src/agent/nodes/direct.py` | direct answer 节点与 prompt/input 构造 |
| `src/agent/graph.py` | direct 路由接入 |
| `tests/unit_tests/` | fake LLM direct answer 测试 |
| `tests/integration_tests/` | graph direct path 测试 |

## 实施步骤

1. 构造 direct answer 输入，包含当前用户目标、必要 memory_context 和压缩摘要。
2. 使用 LLM adapter 协议，不直接读取环境变量。
3. fake LLM 测试必须无需真实 API key。
4. direct path 默认不强制 reflection，除非 route decision 标记。
5. LLM 异常进入 fallback_reason 或错误字段，不崩溃。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

可选真实 smoke：

```bash
uv run pytest tests/integration_tests -m live_llm
```

## 非范围

- 不实现 MCP、planner、multi-agent。
- 不实现 reflection evaluator。
- 不实现 memory write。

## 完成标准

- [ ] Direct answer path 写入 `final_answer`。
- [ ] 简单请求不进入工具或计划路径。
- [ ] fake LLM 测试通过。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 08 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add direct answer path`。

## 进度更新

`docs/progress.md` **08** -> implementation complete 后改为 `✅`.

