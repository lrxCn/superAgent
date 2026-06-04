# Module Map

## Graph orchestration

| Module | Role |
|--------|------|
| `src/agent/graph.py` | `StateGraph` wiring, control nodes (`intake`, `load_memory`, `context_budget`, `intent_router`, `fallback`, `final_answer`), `build_graph` / `create_graph_with_checkpointer` |
| `src/agent/state.py` | `AgentState` and nested TypedDict contracts |
| `src/agent/config.py` | Environment defaults → `AppConfig` / `RuntimeConfig` |
| `src/agent/router.py` | Deterministic intent/complexity routing |
| `src/agent/observability.py` | Runtime events, path metrics, safe summaries, LangSmith gating |

## Execution paths (`src/agent/nodes/`)

| Module | Nodes | Dependencies |
|--------|-------|----------------|
| `nodes/direct.py` | `direct_answer` | `llm.py` |
| `nodes/react.py` | `react_agent` | `llm.py`, `tools/mcp.py` |
| `nodes/planner.py` | `plan_generate`, `plan_validate`, `execute_plan`, `step_observe` | `planning.py`, `llm.py`, `tools/mcp.py` |
| `nodes/orchestrator.py` | `multi_agent_orchestrator` | `workers/*` |
| `nodes/memory_write.py` | `memory_write` | `memory/policy.py`, `memory/graphiti.py` |

## Supporting runtime

| Module | Role |
|--------|------|
| `context_budget.py` | Token estimation, deterministic compression |
| `planning.py` | Plan schema helpers, step scheduling, validation messages |
| `reflection.py` | Reflection gate, rule-based evaluator, revise loop |
| `llm.py` | SiliconFlow OpenAI-compatible client + `FakeLLMClient` |
| `tools/mcp.py` | MCP client, tool protocol, observation sanitization |
| `memory/checkpoint.py` | Async PostgreSQL checkpointer factory + fallback |
| `memory/graphiti.py` | Long-term memory client (HTTP/MCP + mock) |
| `memory/read.py` | `load_memory` Graphiti search orchestration and degraded read errors |
| `memory/policy.py` | Write candidates, sensitive filter, stability checks |
| `workers/protocol.py` | Worker contracts and result mapping |
| `workers/production.py` | Role-specific SiliconFlow-backed production workers |
| `workers/mock.py` | Deterministic mock workers for dev/tests |
| `workers/registry.py` | Worker lookup by role |

## Tests (by concern)

| Area | Unit | Integration |
|------|------|-------------|
| State / graph skeleton | `tests/unit_tests/test_state_schema.py` | `tests/integration_tests/test_graph.py` |
| Router | `tests/unit_tests/test_router.py` | `test_graph.py` (path routing) |
| LLM | `tests/unit_tests/test_llm.py` | — |
| Context budget | `tests/unit_tests/test_context_budget.py` | — |
| Direct answer | `tests/unit_tests/test_direct_answer.py` | `test_graph.py` |
| MCP / ReAct | `tests/unit_tests/test_mcp_tools.py`, `test_react_loop.py` | `test_mcp_smoke.py`, `test_observability_paths.py` |
| Planning | `tests/unit_tests/test_planning.py`, `test_plan_execute.py` | `test_graph.py`, `test_observability_paths.py`, `test_production_workers.py` |
| Multi-agent | `tests/unit_tests/test_orchestrator.py`, `test_production_workers.py` | `test_graph.py`, `test_production_workers.py` |
| Reflection | `tests/unit_tests/test_reflection.py` | `test_graph.py` |
| Memory read/write | `tests/unit_tests/test_memory_read.py`, `test_memory_write.py` | `test_graphiti_memory.py`, `test_graph.py` |
| Observability | `tests/unit_tests/test_observability.py` | `test_observability_paths.py` |
| Checkpoint | `tests/unit_tests/test_checkpoint.py` | `test_postgres_checkpoint.py` (optional) |
| Graphiti | `tests/unit_tests/test_graphiti_memory.py` | `test_graphiti_memory.py` (optional) |

## Planned / stub boundaries

| Area | Current behavior | Follow-up |
|------|------------------|-----------|
| `load_memory` | Reads Graphiti long-term memory by latest user message; failures are recorded in `memory_context.errors` | Add checkpoint short-term summary if needed |
| Workers | Production LLM registry by default; mock registry remains injectable for tests | Add richer role prompts/evals as usage data accumulates |
| MCP tools | Example filesystem server via `MCP_EXAMPLE_*` | Backend-provided MCP servers |
| LangGraph Platform | Not targeted | Local `langgraph dev` only (phase 1) |
