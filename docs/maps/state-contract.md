# State Contract Map

Source of truth: `src/agent/state.py` (`AgentState`).

Callers may invoke the graph with only `messages`; `intake` normalizes the rest.

## Input and control

| Field | Type | Set by | Purpose |
|-------|------|--------|---------|
| `messages` | `list[Message]` | Caller | User/assistant/tool conversation |
| `runtime_config` | `RuntimeConfig` | `intake` | Per-run limits (`react_max_steps`, `reflection_max_rounds`, …) |
| `memory_context` | `MemoryContext` | `load_memory` | Short/long-term snippets, entities, read errors |
| `context_budget` | `ContextBudget` | `context_budget`, `compress_memory` | Estimated tokens, compression summary |
| `intent_decision` | `IntentDecision` | `intent_router` | `path`, `confidence`, `signals`, `requires_reflection` |
| `runtime_events` | `list[RuntimeEvent]` | All instrumented nodes | Structured observability trail |
| `path_metrics` | `PathMetrics` | Observability helpers | Aggregated metrics for active path |

## Execution artifacts

| Field | Type | Set by | Purpose |
|-------|------|--------|---------|
| `plan` | `Plan` | Planner nodes | Steps, validation errors, status |
| `current_step` | `PlanStep \| None` | `execute_plan`, `step_observe` | Active plan step |
| `step_*_pending` | various | `execute_plan` | Staged step result for `step_observe` |
| `mcp_sessions` | `list[MCPSession]` | ReAct / plan tool steps | Connection summary |
| `tool_calls` | `list[ToolCall]` | ReAct / plan tool steps | Invocation history |
| `observations` | `list[Observation]` | Tools, plan, workers | Sanitized observations |
| `agent_results` | `list[AgentResult]` | `multi_agent_orchestrator` | Worker + orchestrator outputs |

## Quality and output

| Field | Type | Set by | Purpose |
|-------|------|--------|---------|
| `evaluation` | `Evaluation` | `reflection_gate`, `evaluator` | Gate/eval status, issues, suggestions |
| `reflection_round` | `int` | `revise` | Revision count |
| `reflection_exhausted` | `bool` | `fallback` | Max revision rounds reached |
| `fallback_reason` | `str \| None` | Router, paths, `fallback` | Why degraded path ran |
| `memory_write_result` | `MemoryWriteResult` | `memory_write` | Graphiti write outcome |
| `final_answer` | `str` | Path nodes, `final_answer` | User-visible answer |

## Route paths

`IntentDecision.path` is one of:

- `direct_answer`
- `react_agent`
- `planner` (graph node name `plan_generate`, not `planner`)
- `multi_agent_orchestrator`
- `fallback`

## Minimal invoke

```python
from agent.graph import build_graph

graph = build_graph()
result = await graph.ainvoke({"messages": [{"role": "user", "content": "hello"}]})
assert "final_answer" in result
```

Tests inject fakes via `build_graph(llm_client=..., mcp_client=..., memory_client=..., worker_registry=...)`.
