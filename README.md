# SuperAgent

SuperAgent is a LangGraph-based multi-path agent runtime for local `langgraph dev`. Tasks 01–14 are implemented: routing, direct answer, MCP ReAct, plan-and-execute, parallel multi-agent, reflection, memory write policies, and runtime observability.

Design history and decisions live in [docs/prd/super-agent-runtime-architecture.md](docs/prd/super-agent-runtime-architecture.md). Architecture maps for the **current code** are in [docs/maps/](docs/maps/).

## Current Status

| Item | Status |
|------|--------|
| Runtime | Multi-path LangGraph runtime (`src/agent/graph.py`) |
| Implementation queue | Phase 1: 15/15 · Incremental: [0/9 — progress.md](docs/progress.md) |
| Incremental PRD | [docs/prd/super-agent-incremental.md](docs/prd/super-agent-incremental.md) |
| Deferred | [docs/todolist.md](docs/todolist.md) |
| Architecture maps | [docs/maps/runtime-graph.md](docs/maps/runtime-graph.md), [module-map.md](docs/maps/module-map.md), [state-contract.md](docs/maps/state-contract.md) |
| Source PRD | [docs/prd/super-agent-runtime-architecture.md](docs/prd/super-agent-runtime-architecture.md) (with implementation status) |

### Implemented vs planned

| Capability | Status |
|------------|--------|
| State schema, graph wiring, SiliconFlow LLM | Implemented |
| Intent router (direct / ReAct / plan / multi-agent / fallback) | Implemented |
| Context budget + deterministic compression | Implemented |
| MCP ReAct loop + observation sanitization | Implemented (example filesystem MCP) |
| Plan-and-execute (generate, validate, execute, observe) | Implemented |
| Parallel multi-agent orchestrator | Implemented (mock workers) |
| Reflection gate, evaluator, revise, max rounds | Implemented |
| Memory write policies + Graphiti client | Implemented (write path; read stub) |
| PostgreSQL checkpointer factory | Implemented (optional; memory fallback) |
| Runtime events + path metrics | Implemented |
| LangGraph Platform deployment | Planned (out of phase 1 scope) |
| Production MCP servers | Planned (backend-provided; example server only) |
| Long-term memory read on `load_memory` | Planned (node returns empty context today) |
| Production worker backends | Planned (mock registry today) |

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

- Short-term: LangGraph checkpoint + PostgreSQL (`langgraph-checkpoint-postgres`, `DATABASE_URL`, `CHECKPOINT_SETUP`).
- Long-term write: Graphiti client (`memory/graphiti.py`, policies in `memory/policy.py`). See [docs/graphiti-orbstack-runbook.md](docs/graphiti-orbstack-runbook.md).
- `load_memory` currently supplies an empty `memory_context` unless the caller pre-populates it.

### Tools

- External tools via MCP (`tools/mcp.py`).
- Example connectivity server (phase 1):

```bash
npx -y @modelcontextprotocol/server-filesystem ./docs
```

Configure with `MCP_EXAMPLE_SERVER_COMMAND` and `MCP_EXAMPLE_SERVER_ARGS`.

### Multi-Agent

- Parallel orchestration with timeout and concurrency limits.
- Defaults: `WORKER_MAX_CONCURRENCY=4`, `WORKER_TIMEOUT_SECONDS=120`.
- Worker timeout → `failed`; aggregation may be `partial`.

### Reflection

- Enabled for tool/plan/multi-agent paths, `confidence < 0.72`, high-risk keywords, explicit review requests, and related triggers.
- Default `REFLECTION_MAX_ROUNDS=1`.

### Observability

- Structured `runtime_events` and `path_metrics` on state (`observability.py`).
- Tool summaries redact secrets and omit full payloads.
- LangSmith when `LANGCHAIN_TRACING_V2=true` and `LANGSMITH_API_KEY` is set locally.

### Configuration

Non-secret defaults: `.env_example` and `.env.example` (keep identical). Real keys only in local `.env` (gitignored).

```dotenv
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=SUPER_AGENT
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

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

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable
CHECKPOINT_SETUP=true

MCP_EXAMPLE_SERVER_COMMAND=npx
MCP_EXAMPLE_SERVER_ARGS=-y @modelcontextprotocol/server-filesystem ./docs
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

Optional smoke (real services): PostgreSQL checkpoint, Graphiti, MCP filesystem server — see integration tests marked optional/skipped in CI.

## Maintenance

Phase 1 skeleton is complete. **Incremental queue (16–24)** targets local-usable runtime — see [docs/progress.md](docs/progress.md) and [docs/prd/super-agent-incremental.md](docs/prd/super-agent-incremental.md). Execute one prompt per agent window; Agent 验收通过后再标 ✅.
