# SuperAgent 增量 PRD

> **基线**：Phase 1（prompts 01–15）已完成，见 [super-agent-runtime-architecture.md](./super-agent-runtime-architecture.md)。  
> **当前状态**：G1–G9 已完成，本文保留为增量实施记录和验收索引，不再表示待办清单。

## 1. 目标

在本地 `langgraph dev` 上把 SuperAgent 从「骨架 + mock」推进到可日常使用：

| # | 能力 | 验收 |
|---|------|------|
| G1 | 本地 Graphiti + Postgres 跑通 | OrbStack runbook 可跟做；health / smoke 通过 |
| G2 | `load_memory` 真读 | Graphiti search 填入 `long_term`；失败降级不阻断 |
| G3 | 记忆读写闭环 | 写入后新 thread 能读到长期记忆 |
| G4 | 生产 Worker | 四角色 LLM Worker 替换 mock；Plan `agent` 步可执行 |
| G5 | 多 MCP + URL 传输 | 多 server 配置；stdio + URL；公开 MCP 作 stand-in |
| G6 | Guardrails | allowlist、话题 block、每 run 工具次数上限 + security 事件 |
| G7 | LLM Evaluator | 替换纯规则 evaluator；revise 对齐 LLM 输出 |
| G8 | 租户 ID + LangSmith/Studio | `user_id` / `thread_id` / Graphiti `group_id`；用 Studio 调试，无自建 UI |
| G9 | 文档诚实 | README / todo 断链修复；区分已实现 vs stub |

## 2. 非目标

- LangGraph Platform / PR CI / 后端生产 MCP → [todolist.md](../todolist.md)

## 3. 实施顺序

```text
G1 → G2 → G3 → G4 → G5 → G6 → G7 → G8 → G9
```

G5 与 G6 可部分并行；G8 依赖 G1–G3 的 thread / group 契约。

## 4. 范围摘要

### G1 本地依赖

- 补全 [graphiti-orbstack-runbook.md](../graphiti-orbstack-runbook.md)（compose、`.env`、排查）
- Postgres checkpoint 本地 runbook + `langgraph dev` 挂载说明

### G2–G3 记忆读

- `load_memory` 调 Graphiti `search`；可选 checkpoint 摘要进 `short_term`
- integration：write → 新 thread → `long_term` 非空

### G4 Worker

- `researcher` / `coder` / `reviewer` / `memory_manager` 生产实现
- 默认 registry 指向生产；测试仍 inject mock
- `ExecutePlanNode`：`type: agent` 调单 Worker，不再 `skipped`

### G5 MCP

- 实现 MCP URL/SSE transport（`tools/mcp.py`）
- 多 server 配置；ReAct / Plan tool 步按 server 路由
- Stand-in：filesystem（stdio）+ 至少一个公开 HTTP MCP（实施时选定）

### G6 Guardrails

- 配置层：工具 allowlist、话题 block、`max_tool_calls_per_run`
- 违规 → `runtime_events`（`event=security`）；ReAct / Plan 统一拦截

### G7 LLM Evaluator

- evaluator 节点 LLM 结构化输出（PASS/FAIL、issues、suggestions）
- 保留 fake client 单测；revise 消费 LLM 反馈

### G8 租户 ID + LangSmith/Studio

- Runtime 贯通 `user_id`、`thread_id`、Graphiti `group_id`
- **不**做内置 Web UI；用 `langgraph dev` Studio + LangSmith tracing
- README 只写字段/env **契约**；Studio 点选步骤在任务交付对话里说明，不另建 runbook 文件

### G9 文档

- 文档链接指向 [todolist.md](../todolist.md) 与增量 PRD，无断链
- README「已实现 vs stub」表与 [module-map.md](../maps/module-map.md) 对齐

## 5. 验收（整体）

Status source: [progress.md](../progress.md) tasks 16–24.

- [x] OrbStack 上 Graphiti +（可选）Postgres 按 runbook 起服
- [x] `load_memory` 非 mock 场景有 `long_term` 内容
- [x] multi_agent / plan agent 步走真 Worker（非 mock 文案）
- [x] ≥2 个 MCP server 同时配置且 tool 步可达
- [x] Guardrails 违规可观测且调用被拦
- [x] Reflection 路径 evaluator 走 LLM（mock 测试仍绿）
- [x] Studio + LangSmith 可验证 thread / user 隔离；Graphiti 不跨 `group_id`
- [x] 文档无断链、stub 边界清晰

## 6. 任务卡

| G | Prompt |
|---|--------|
| G1 | [16-local-services-runbooks](../prompts/16-local-services-runbooks.md) |
| G2 | [17-load-memory-read](../prompts/17-load-memory-read.md) |
| G3 | [18-memory-read-write-loop](../prompts/18-memory-read-write-loop.md) |
| G4 | [19-production-workers](../prompts/19-production-workers.md) |
| G5 | [20-multi-mcp-and-url-transport](../prompts/20-multi-mcp-and-url-transport.md) |
| G6 | [21-configurable-guardrails](../prompts/21-configurable-guardrails.md) |
| G7 | [22-llm-evaluator](../prompts/22-llm-evaluator.md) |
| G8 | [23-tenant-ids-and-langsmith-studio](../prompts/23-tenant-ids-and-langsmith-studio.md) |
| G9 | [24-incremental-docs-closure](../prompts/24-incremental-docs-closure.md) |

进度：[progress.md](../progress.md)
