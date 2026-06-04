# SuperAgent Progress

> Maintain this file when executing `docs/prompts/` task cards.

## Overview

| Metric | Value |
|--------|-------|
| Phase 1 tasks | 15 / 15 ✅ |
| Incremental tasks | 4 / 9 |
| In progress | - |
| Blocked | 0 |

**Recommended next task**: [20 - Multi MCP and URL transport](./prompts/20-multi-mcp-and-url-transport.md)

**PRD**: [super-agent-incremental.md](./prd/super-agent-incremental.md) · **Deferred**: [todolist.md](./todolist.md)

## Phase 1 — Runtime (complete)

Status: `⬜ 待开始` · `🔄 进行中` · `✅ 完成` · `⏸ 阻塞` · `⏭ 跳过`

| ID | Task | Status | Completed At | Notes |
|----|------|--------|--------------|-------|
| 01 | [Baseline docs and config hygiene](./prompts/01-baseline-docs-config.md) | ✅ 完成 | 2026-06-03 | 骨架 |
| 02 | [State schema and graph skeleton](./prompts/02-state-schema-graph-skeleton.md) | ✅ 完成 | 2026-06-03 | 骨架 |
| 03 | [SiliconFlow LLM adapter](./prompts/03-siliconflow-llm-adapter.md) | ✅ 完成 | 2026-06-03 | 本地可用 |
| 04 | [PostgreSQL checkpoint memory](./prompts/04-postgres-checkpoint-memory.md) | ✅ 完成 | 2026-06-03 | 骨架（集成 optional） |
| 05 | [Graphiti long-term memory client](./prompts/05-graphiti-long-term-memory.md) | ✅ 完成 | 2026-06-03 | 骨架（write only；runbook 薄） |
| 06 | [Context budget and compression](./prompts/06-context-budget-compression.md) | ✅ 完成 | 2026-06-03 | 本地可用 |
| 07 | [Intent and complexity router](./prompts/07-intent-complexity-router.md) | ✅ 完成 | 2026-06-03 | 本地可用 |
| 08 | [Direct answer path](./prompts/08-direct-answer-path.md) | ✅ 完成 | 2026-06-03 | 本地可用 |
| 09 | [MCP tools and ReAct loop](./prompts/09-mcp-tools-react-loop.md) | ✅ 完成 | 2026-06-03 | 骨架（stdio 示例） |
| 10 | [Plan-and-Execute path](./prompts/10-plan-and-execute.md) | ✅ 完成 | 2026-06-03 | 骨架（agent 步 skip） |
| 11 | [Parallel multi-agent orchestrator](./prompts/11-parallel-multi-agent.md) | ✅ 完成 | 2026-06-03 | 骨架（mock workers） |
| 12 | [Reflection evaluator and revise](./prompts/12-reflection-evaluator-revise.md) | ✅ 完成 | 2026-06-03 | 骨架（规则 evaluator） |
| 13 | [Memory write policies](./prompts/13-memory-write-policies.md) | ✅ 完成 | 2026-06-03 | 骨架 |
| 14 | [Observability and path metrics](./prompts/14-observability-path-metrics.md) | ✅ 完成 | 2026-06-03 | 本地可用 |
| 15 | [Final docs and architecture maps](./prompts/15-final-docs-architecture-maps.md) | ✅ 完成 | 2026-06-03 | 文档 |

## Incremental — Local usable runtime

Source PRD: [super-agent-incremental.md](./prd/super-agent-incremental.md)

| ID | Task | Status | Completed At | Notes |
|----|------|--------|--------------|-------|
| 16 | [Local services runbooks](./prompts/16-local-services-runbooks.md) | ✅ 完成 | 2026-06-04 | 本地可用 |
| 17 | [Load memory read](./prompts/17-load-memory-read.md) | ✅ 完成 | 2026-06-04 | 本地可用 |
| 18 | [Memory read write loop](./prompts/18-memory-read-write-loop.md) | ✅ 完成 | 2026-06-04 | 本地可用 |
| 19 | [Production workers](./prompts/19-production-workers.md) | ✅ 完成 | 2026-06-04 | 本地可用 |
| 20 | [Multi MCP and URL transport](./prompts/20-multi-mcp-and-url-transport.md) | ⬜ 待开始 | - | G5 |
| 21 | [Configurable guardrails](./prompts/21-configurable-guardrails.md) | ⬜ 待开始 | - | G6；依赖 20 |
| 22 | [LLM evaluator](./prompts/22-llm-evaluator.md) | ⬜ 待开始 | - | G7 |
| 23 | [Tenant IDs and LangSmith Studio](./prompts/23-tenant-ids-and-langsmith-studio.md) | ⬜ 待开始 | - | G8；依赖 18；无自建 UI |
| 24 | [Incremental docs closure](./prompts/24-incremental-docs-closure.md) | ⬜ 待开始 | - | G9；依赖 16–23 |

## Changelog

| Date | Change |
|------|--------|
| 2026-06-04 | Completed task 19 production workers; default registry uses LLM workers, plan agent steps execute, and real LLM Agent 验收通过。 |
| 2026-06-04 | Completed task 18 memory read/write Graphiti loop; unit tests and Graphiti-backed Agent 验收通过。 |
| 2026-06-04 | Completed task 17 load_memory Graphiti read; unit, lint, mypy, and Graphiti-backed Agent 验收通过。 |
| 2026-06-04 | Completed task 16 local services runbooks; Graphiti and Postgres service-backed Agent 验收通过。 |
| 2026-06-03 | Planned incremental queue from `super-agent-incremental.md`: task cards 16–24, progress section; Phase 1 Notes 补档位诚实标注。 |
| 2026-06-03 | Completed task 15 final docs and architecture maps. |
| 2026-06-03 | Created SuperAgent planning docs and 15-task queue from runtime architecture PRD. |
