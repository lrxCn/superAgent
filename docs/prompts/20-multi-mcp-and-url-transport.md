# 20 - Multi MCP And URL Transport

## 建议执行模型

- 模型：GPT-5
- Reasoning：high
- 原因：URL/SSE transport、多 server 配置、ReAct/Plan 路由。

## 新窗口执行规则

1. 先读 `AGENTS.md`、`README.md`、`docs/progress.md`、`docs/prd/super-agent-incremental.md` 和本任务卡。
2. 核对任务 09 已完成。
3. 只实现本任务范围；跑 Agent 验收。
4. 用户要求 commit 时再提交。

## 依赖

09。

## 背景

G5：仅 `MCP_EXAMPLE_*` 单 server；URL transport 未实现。

## 目标

- 实现 MCP URL/SSE transport。
- 多 server 配置；ReAct / Plan tool 步按 server 路由。
- Stand-in：filesystem（stdio）+ ≥1 公开 HTTP MCP（实施时选定并文档化）。

## 范围

| Area | Change |
|------|--------|
| `src/agent/tools/mcp.py` | URL/SSE client |
| `src/agent/config.py` | 多 server 配置结构 |
| `src/agent/nodes/react.py`, `planner.py` | 按 server 解析工具 |
| `.env_example`, `README.md` | 多 server 示例 |
| `tests/` | unit + 至少一条真 server smoke |

## 验证方案

```bash
uv run pytest tests/unit_tests -q -k mcp
uv run ruff check src tests
```

## Agent 验收

```bash
# Node + 配置的 stdio server
uv run pytest tests/integration_tests/test_mcp_smoke.py -q
# 第二个 HTTP MCP（按 README 命令起或连公开端点）
uv run pytest tests/integration_tests/test_mcp_multi.py -q
```

## 非范围

- 后端生产 MCP（见 `docs/todolist.md`）
- Guardrails（任务 21）

## 完成标准

- [ ] ≥2 server 可 list_tools + call_tool，档位：**本地可用**
- [ ] progress 20 更新

## 进度更新

`docs/progress.md` **20** → 验收后 `✅`。
