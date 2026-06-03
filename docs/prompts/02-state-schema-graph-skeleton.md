# 02 - State Schema And Graph Skeleton

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：该任务定义跨节点状态契约和 LangGraph 骨架，是后续所有路径的架构基础。

## 新窗口执行规则

1. 先读根目录 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-runtime-architecture.md` 和本任务卡。
2. 核对 `docs/progress.md` 中本任务依赖是否完成；未完成则停止。
3. 对比当前模型和 reasoning 与本节建议；如果不一致或未知，先告诉用户建议配置并等待确认，除非用户明确要求继续。
4. 只实现本任务范围，不顺手做相邻任务。
5. 按本任务测试计划验证。
6. 测试通过后更新 `docs/progress.md`。
7. 自动创建 git commit；不要自动 push，除非用户明确要求。

## 依赖

01。

## 背景

当前 `src/agent/graph.py` 是模板单节点 `changeme` 示例。需要先建立 SuperAgent 的 State、Context、节点占位和路由骨架，让后续任务能逐步填充能力。

## 目标

- 用明确的 state/context schema 替换模板示例字段，并建立可运行的多节点骨架。

## 范围

| Area | Change |
|------|--------|
| `src/agent/state.py` | 定义 messages、runtime_config、memory_context、context_budget、intent_decision、plan、tool_calls、observations、agent_results、evaluation、fallback_reason、memory_write_result、final_answer 等字段 |
| `src/agent/config.py` | 定义运行默认值与环境变量读取结构，不读取真实密钥到测试输出 |
| `src/agent/graph.py` | 建立 intake、load_memory、context_budget、intent_router、direct_answer、fallback、memory_write、final_answer 等占位节点 |
| `tests/unit_tests/` | 增加 state/config/graph skeleton 契约测试 |
| `tests/integration_tests/` | 保持 graph 最小调用可运行 |

## 实施步骤

1. 设计 typed state，优先使用 `TypedDict` 或 dataclass，保持 LangGraph 兼容。
2. 删除模板 `changeme` 状态对外契约，必要时保留兼容测试但改成 SuperAgent 输入。
3. 新建占位节点时只返回结构化默认结果，不调用真实 LLM、工具、数据库或 Graphiti。
4. `graph` 必须能被 `langgraph.json` 正常加载。
5. 更新测试，冻结最小 state 字段和默认配置。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

如果依赖暂时不可用，至少运行：

```bash
uv run python -m compileall src tests
```

## 非范围

- 不实现真实 LLM。
- 不实现真实 memory、MCP、planner、multi-agent 或 reflection。
- 不改 PRD 决策。

## 完成标准

- [ ] Graph skeleton 可加载并可最小调用。
- [ ] State/context 契约有测试。
- [ ] 模板 `changeme` 不再是核心运行契约。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 02 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add runtime state skeleton`。

## 进度更新

`docs/progress.md` **02** -> implementation complete 后改为 `✅`.

