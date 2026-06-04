# SuperAgent

SuperAgent is a LangGraph-based multi-path agent runtime for local `langgraph dev`. Tasks 01–24 are complete: the runtime now has routing, direct answer, MCP ReAct, plan-and-execute, parallel multi-agent, reflection, memory read/write, guardrails, tenant IDs, and observability for local development.

Design history and decisions live in [docs/prd/super-agent-runtime-architecture.md](docs/prd/super-agent-runtime-architecture.md). Architecture maps for the **current code** are in [docs/maps/](docs/maps/).

## Current Status

| Item | Status |
|------|--------|
| Runtime | Multi-path LangGraph runtime (`src/agent/graph.py`) |
| Implementation queue | Phase 1: 15/15 · Incremental: [9/9 — progress.md](docs/progress.md) |
| Incremental PRD | [docs/prd/super-agent-incremental.md](docs/prd/super-agent-incremental.md) |
| Deferred | [docs/todolist.md](docs/todolist.md) |
| Architecture maps | [docs/maps/runtime-graph.md](docs/maps/runtime-graph.md), [module-map.md](docs/maps/module-map.md), [state-contract.md](docs/maps/state-contract.md) |
| Source PRD | [docs/prd/super-agent-runtime-architecture.md](docs/prd/super-agent-runtime-architecture.md) (with implementation status) |

### Capability Status

档位：`本地可用` = 已接真实本地依赖或真实 LLM/MCP 路径并通过任务卡验收；`骨架` = contract 可用但仍偏最小实现；`计划` = 明确非当前增量范围。

| Capability | Tier | Current boundary |
|------------|------|------------------|
| State schema, graph wiring, SiliconFlow LLM | 本地可用 | `build_graph(...)` supports injectable fakes for tests |
| Intent router (direct / ReAct / plan / multi-agent / fallback) | 本地可用 | Deterministic router; not an LLM classifier |
| Context budget + deterministic compression | 本地可用 | Rule-based estimation/compression |
| MCP ReAct loop + observation sanitization | 本地可用 | Multi-server stdio/SSE/Streamable HTTP; public/local stand-ins documented |
| Plan-and-execute | 本地可用 | Plan generation/validation/execution; plan quality remains rule-oriented |
| Parallel multi-agent orchestrator | 本地可用 | SiliconFlow workers by default; mock registry remains injectable |
| Reflection gate, LLM evaluator, revise | 本地可用 | LLM evaluator with rule fallback/test fakes |
| Memory read/write policies + Graphiti client | 本地可用 | Graphiti read/write with tenant `group_id`; read/write failures degrade |
| PostgreSQL checkpointer factory | 本地可用 | Optional local service; in-memory fallback if unavailable |
| Guardrails | 本地可用 | Configurable topic block, tool allowlist, and per-run tool cap |
| Runtime identity + Studio/LangSmith debugging | 本地可用 | `thread_id`/`user_id` configurable; no built-in Web UI |
| Runtime events + path metrics | 本地可用 | Structured state events; LangSmith enabled by local env |
| LangGraph Platform deployment | 计划 | Out of local-runtime scope |
| Production backend MCP servers | 计划 | Backend-provided servers deferred in `docs/todolist.md` |

## Documentation Order

1. `AGENTS.md` — agent working rules.
2. `README.md` — runtime contract (this file).
3. `docs/progress.md` — task queue and changelog.
4. `docs/maps/` — graph, module, and state maps.
5. `docs/prompts/` — historical implementation task cards.
6. `docs/prd/` — design intent and rationale.

## Graph Topology

Entry: `langgraph.json` exposes `agent` from `./src/agent/graph.py:graph`.

```mermaid
flowchart TD
  start_node([START]) --> intake
  intake --> load_memory
  load_memory --> context_budget
  context_budget -->|over budget| compress_memory
  context_budget -->|ok| intent_router
  compress_memory --> intent_router
  intent_router -->|direct_answer| direct_answer
  intent_router -->|react_agent| react_agent
  intent_router -->|planner| plan_generate
  intent_router -->|multi_agent| multi_agent_orchestrator
  intent_router -->|fallback| fallback
  plan_generate --> plan_validate
  plan_validate --> execute_plan
  plan_validate --> fallback
  execute_plan --> step_observe
  step_observe --> execute_plan
  step_observe --> reflection_gate
  direct_answer --> reflection_gate
  react_agent --> reflection_gate
  multi_agent_orchestrator --> reflection_gate
  fallback --> reflection_gate
  reflection_gate --> evaluator
  reflection_gate --> memory_write
  evaluator --> memory_write
  evaluator --> revise
  evaluator --> fallback
  revise --> reflection_gate
  memory_write --> final_answer
  final_answer --> end_node([END])
```

Full edge labels and path notes: [docs/maps/runtime-graph.md](docs/maps/runtime-graph.md).

## Execution Paths

| Path | Purpose |
|------|---------|
| Direct answer | Low-risk requests without tools or planning |
| ReAct tools | MCP-backed tool loop with bounded steps |
| Plan-and-Execute | Structured plan, validation, step execution and observation |
| Multi-Agent | Parallel workers (researcher, coder, reviewer, memory manager) |
| Reflection | Quality gate for complex, tool, plan, multi-agent, high-risk, or low-confidence routes |
| Fallback | Clarification, partial result, or safe downgrade when execution cannot continue |
| Guardrails | Configurable topic block, MCP tool allowlist, and per-run tool call cap with security events |

Nodes use explicit `AgentState` fields — see [docs/maps/state-contract.md](docs/maps/state-contract.md).

## Contracts

### Runtime

- Phase 1 target: local `langgraph dev` only (no LangGraph Platform).
- `langgraph.json` → `src/agent/graph.py:graph`.
- Optional PostgreSQL checkpointer: `create_graph_with_checkpointer()` in `graph.py`.
- Inject test doubles: `build_graph(llm_client=..., mcp_client=..., worker_registry=..., memory_client=...)`.

### LLM

- Provider: SiliconFlow (OpenAI-compatible).
- Variables: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL_NAME`.
- Default model: `Pro/moonshotai/Kimi-K2.6`.
- Do not commit real API keys.

### Memory

- Short-term: LangGraph checkpoint + PostgreSQL (`langgraph-checkpoint-postgres`, `DATABASE_URL`, `CHECKPOINT_SETUP`). See [docs/postgres-local-runbook.md](docs/postgres-local-runbook.md).
- Long-term read/write: Graphiti client (`memory/graphiti.py`), `load_memory` read orchestration (`memory/read.py`), write policies in `memory/policy.py`. See [docs/graphiti-orbstack-runbook.md](docs/graphiti-orbstack-runbook.md).
- `load_memory` uses the latest user message as the Graphiti search query, fills `memory_context.long_term`, and records read failures in `memory_context.errors` without blocking the graph.
- Runtime identity: pass `configurable.thread_id` for checkpoint threads and `configurable.user_id` for tenant identity. Graphiti uses a safe `group_id` derived from `user_id` by default; an explicit `configurable.group_id` can override the source value for specialized runs.

### Tools

- External tools via MCP (`tools/mcp.py`).
- Supported transports: stdio, SSE, and Streamable HTTP.
- Configure one or more servers with `MCP_SERVERS` JSON. Tool names are exposed as `server.tool`; when a raw tool name is unique, the legacy bare name also works.
- ReAct and Plan tool steps route by the configured server prefix, for example `filesystem.read_file` or `crow_catalog.products.search`.
- Example stdio server:

```bash
npx -y @modelcontextprotocol/server-filesystem ./docs
```

- Public Streamable HTTP stand-in used for smoke tests and docs: `https://crowcrowcrow.com/api/mcp/mcp` (`crow_catalog`). This is not a production backend dependency.
- `MCP_EXAMPLE_SERVER_COMMAND` and `MCP_EXAMPLE_SERVER_ARGS` are still accepted as a single-server fallback when `MCP_SERVERS` is unset.

### Multi-Agent

- Parallel orchestration with timeout and concurrency limits.
- Default registry uses role-specific LLM workers: `researcher`, `coder`, `reviewer`, and `memory_manager`.
- Plan `type: agent` steps execute a single worker and complete/fail like other plan steps.
- Defaults: `WORKER_MAX_CONCURRENCY=4`, `WORKER_TIMEOUT_SECONDS=120`.
- Worker timeout → `failed`; aggregation may be `partial`.

### Reflection

- Enabled for tool/plan/multi-agent paths, `confidence < 0.72`, high-risk keywords, explicit review requests, and related triggers.
- Default `REFLECTION_MAX_ROUNDS=1`.

### Observability

- Structured `runtime_events` and `path_metrics` on state (`observability.py`).
- Tool summaries redact secrets and omit full payloads.
- LangSmith when `LANGCHAIN_TRACING_V2=true` and `LANGSMITH_API_KEY` is set locally.

### Studio / LangSmith Debugging

SuperAgent does not include a Web UI. Use `uv run langgraph dev` and invoke the `agent` graph with `configurable.thread_id` and `configurable.user_id`; the graph mirrors them into state as `thread_id`, `user_id`, and a Graphiti-safe `group_id`. LangSmith traces go to `LANGCHAIN_PROJECT`/`LANGSMITH_PROJECT` (default `SUPER_AGENT`) when `LANGCHAIN_TRACING_V2=true` or `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` is set. In LangSmith, filter or group runs by `thread_id` metadata and compare `user_id`/`group_id` in the root input/state to verify tenant memory isolation.

### Configuration

Non-secret defaults: `.env_example` and `.env.example` (keep identical). Real keys only in local `.env` (gitignored).

```dotenv
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=SUPER_AGENT
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
SUPERAGENT_DEFAULT_USER_ID=main

OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL_NAME=Pro/moonshotai/Kimi-K2.6
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=4096

REACT_MAX_STEPS=8
PLAN_MAX_STEPS=12
WORKER_MAX_CONCURRENCY=4
WORKER_TIMEOUT_SECONDS=120
TOOL_TIMEOUT_SECONDS=30
REFLECTION_MAX_ROUNDS=1

GUARDRAIL_TOOL_ALLOWLIST=
GUARDRAIL_BLOCKED_TOPICS=
MAX_TOOL_CALLS_PER_RUN=0

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable
CHECKPOINT_SETUP=true

MCP_EXAMPLE_SERVER_COMMAND=npx
MCP_EXAMPLE_SERVER_ARGS=-y @modelcontextprotocol/server-filesystem ./docs
MCP_SERVERS=[{"name":"filesystem","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","./docs"]},{"name":"crow_catalog","transport":"streamable_http","url":"https://crowcrowcrow.com/api/mcp/mcp"}]
MCP_TOOL_TIMEOUT_SECONDS=30

GRAPHITI_BACKEND=falkordb
GRAPHITI_MCP_URL=http://localhost:8000
FALKORDB_URL=redis://localhost:6379
```

Place `OPENAI_API_KEY` and `LANGSMITH_API_KEY` only in `.env`, not in committed files.

## Development Workflow

Use `uv` for Python and dependencies.

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
uv run langgraph dev
```

Optional smoke (real services): PostgreSQL checkpoint, Graphiti, MCP filesystem + local/public HTTP servers — see integration tests marked optional/skipped in CI.

## Maintenance

Phase 1 and the incremental local-usable queue (16–24) are complete. Future work should start from [docs/todolist.md](docs/todolist.md) or a new PRD; keep `docs/progress.md` as the changelog for completed task cards.
