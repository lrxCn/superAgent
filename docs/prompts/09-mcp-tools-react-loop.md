# 09 - MCP Tools And ReAct Loop

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：该任务引入外部工具协议、工具 schema、错误处理和 ReAct 循环，是运行时风险较高的扩展点。

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

外部工具通过 MCP 接入。后端正式 MCP server 交付前，示例使用官方 filesystem MCP server：`npx -y @modelcontextprotocol/server-filesystem ./docs`。

## 目标

- 实现 MCP client/adapter、工具发现、工具调用 observation 和最小 ReAct 循环。

## 范围

| Area | Change |
|------|--------|
| `src/agent/tools/mcp.py` | MCP server 配置、连接、工具发现、调用协议 |
| `src/agent/nodes/react.py` | ReAct loop 节点、max steps、observation 写入 |
| `src/agent/graph.py` | tool 路由接入 |
| `.env_example` / `.env.example` | MCP 示例配置 |
| `tests/unit_tests/` | mock MCP client、工具成功/失败/超时/参数错误 |

## 实施步骤

1. 定义内部 `ToolSpec`、`ToolCall`、`ToolObservation`。
2. MCP client 允许配置 command/args 或 URL/transport，为后端 server 留扩展点。
3. 工具结果写入 observation 时限制大小并过滤敏感字段。
4. ReAct loop 支持 `REACT_MAX_STEPS=8`。
5. MCP 连接失败只影响工具路径，不影响 direct path。
6. 单元测试使用 mock MCP client；真实 filesystem MCP 只做可选 smoke。

## 验证方案

```bash
uv run pytest tests/unit_tests tests/integration_tests
uv run ruff check src tests
uv run mypy src
```

可选真实 smoke：

```bash
npx -y @modelcontextprotocol/server-filesystem ./docs
uv run pytest tests/integration_tests -m mcp
```

## 非范围

- 不实现后端正式 MCP server。
- 不实现 planner 或 multi-agent。
- 不让工具直接访问未授权目录。

## 完成标准

- [ ] MCP adapter 有 mock 测试。
- [ ] ReAct loop 写入 tool_calls 和 observations。
- [ ] max steps、失败、超时有测试。
- [ ] 验证命令通过或记录无法运行的具体原因。
- [ ] `docs/progress.md` 任务 09 更新为 `✅ 完成`。
- [ ] Git commit 已创建，建议消息：`feat: add mcp react loop`。

## 进度更新

`docs/progress.md` **09** -> implementation complete 后改为 `✅`.

