# Runtime Graph Map

Compiled graph entry: `langgraph.json` → `./src/agent/graph.py:graph` (`build_graph()`).

Control plane nodes run on every request. Execution paths branch after `intent_router`. All successful paths converge on `reflection_gate` → (`evaluator` optional) → `memory_write` → `final_answer`.

## Topology

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
  intent_router -->|multi_agent_orchestrator| multi_agent_orchestrator
  intent_router -->|fallback| fallback

  plan_generate --> plan_validate
  plan_validate -->|valid| execute_plan
  plan_validate -->|invalid| fallback
  execute_plan --> step_observe
  step_observe -->|more steps| execute_plan
  step_observe -->|done| reflection_gate

  direct_answer --> reflection_gate
  react_agent --> reflection_gate
  multi_agent_orchestrator --> reflection_gate
  fallback --> reflection_gate

  reflection_gate -->|enabled| evaluator
  reflection_gate -->|skip| memory_write
  evaluator -->|pass| memory_write
  evaluator -->|fail + rounds left| revise
  evaluator -->|fail + exhausted| fallback
  revise --> reflection_gate

  memory_write --> final_answer
  final_answer --> end_node([END])
```

## Route paths (`IntentDecision.path`)

| Path | Entry nodes | Notes |
|------|-------------|-------|
| `direct_answer` | `direct_answer` | SiliconFlow LLM, low-risk prompts |
| `react_agent` | `react_agent` | Bounded ReAct loop + MCP tools |
| `planner` | `plan_generate` → `plan_validate` → `execute_plan` ↔ `step_observe` | Deterministic plan generation; LLM/tool/agent steps |
| `multi_agent_orchestrator` | `multi_agent_orchestrator` | Parallel LLM workers (researcher/coder/reviewer/memory manager) |
| `fallback` | `fallback` | Clarification, validation failure, reflection exhaustion |

Router implementation: `src/agent/router.py` (`route_intent`). Conditional edge selectors live beside nodes in `graph.py`, `planner.py`, and `reflection.py`.

## Observability

Each major node appends to `runtime_events` and refreshes `path_metrics` via `src/agent/observability.py` (`NodeTracker`). See [state-contract.md](./state-contract.md).
