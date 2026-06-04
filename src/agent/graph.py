"""LangGraph skeleton for the SuperAgent runtime."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from agent.config import load_config
from agent.context_budget import check_context_budget, compress_state_context
from agent.guardrails import (
    check_topic_guardrail,
    guardrail_intent_decision,
    security_event_updates,
)
from agent.identity import identity_state_updates, resolve_runtime_identity
from agent.llm import LLMClient
from agent.memory.checkpoint import CheckpointerResource, create_postgres_checkpointer
from agent.memory.graphiti import LongTermMemoryClient
from agent.memory.read import create_load_memory_node
from agent.nodes.direct import create_direct_answer_node
from agent.nodes.memory_write import create_memory_write_node
from agent.nodes.orchestrator import create_multi_agent_orchestrator_node
from agent.nodes.planner import (
    choose_plan_execution_path,
    choose_plan_validate_path,
    create_execute_plan_node,
    create_plan_generate_node,
    create_plan_validate_node,
    create_step_observe_node,
)
from agent.nodes.react import create_react_node
from agent.observability import NodeTracker, langsmith_tracing_enabled, safe_summary
from agent.reflection import (
    choose_evaluator_path,
    choose_reflection_path,
    create_evaluator_node,
    create_reflection_gate_node,
    create_revise_node,
)
from agent.router import route_intent
from agent.state import AgentState, RuntimeConfig
from agent.tools.mcp import MCPClient
from agent.workers.production import create_production_worker_registry
from agent.workers.registry import WorkerRegistry


def _runtime_config(state: AgentState) -> RuntimeConfig:
    return state.get("runtime_config") or load_config().to_runtime_config()


async def intake(state: AgentState, config: RunnableConfig) -> AgentState:
    """Normalize caller input into the shared runtime state."""
    tracker = NodeTracker(state, "intake", path="control")
    tracing = langsmith_tracing_enabled()
    identity = resolve_runtime_identity(state, config)
    return tracker.finish(
        {
            "runtime_config": _runtime_config(state),
            **identity_state_updates(identity),
            "tool_calls": state.get("tool_calls", []),
            "observations": state.get("observations", []),
            "agent_results": state.get("agent_results", []),
            "mcp_sessions": state.get("mcp_sessions", []),
            "fallback_reason": state.get("fallback_reason"),
            "runtime_events": state.get("runtime_events", []),
        },
        summary=(
            "initialized runtime fields; "
            f"user_id={identity.user_id} group_id={identity.group_id} "
            f"thread_id={identity.thread_id or 'unset'} "
            f"langsmith_tracing={tracing}"
        ),
    )


async def context_budget(state: AgentState) -> AgentState:
    """Estimate context budget before routing."""
    tracker = NodeTracker(state, "context_budget", path="control")
    budget = check_context_budget(state, limit=load_config().llm_max_tokens)
    return tracker.finish(
        {"context_budget": budget},
        summary=(
            f"estimated={budget['estimated']} limit={budget['limit']} "
            f"compressed={budget['compressed']}"
        ),
    )


def choose_context_budget_path(state: AgentState) -> Literal["compress_memory", "ok"]:
    """Route over-budget state through deterministic compression."""
    budget = state.get("context_budget")
    if budget and budget["estimated"] > budget["limit"]:
        return "compress_memory"
    return "ok"


async def compress_memory(state: AgentState) -> AgentState:
    """Compress context deterministically without calling an LLM."""
    tracker = NodeTracker(state, "compress_memory", path="control")
    budget = state.get("context_budget")
    limit = budget["limit"] if budget else load_config().llm_max_tokens
    compressed = compress_state_context(state, limit=limit)
    updated_budget = compressed.get("context_budget", budget)
    summary = "context compressed"
    if updated_budget:
        summary = (
            f"dropped_messages={updated_budget.get('dropped_messages', 0)} "
            f"dropped_memories={updated_budget.get('dropped_memories', 0)}"
        )
    return tracker.finish(compressed, summary=summary)


async def intent_router(state: AgentState) -> AgentState:
    """Choose an execution path from structured intent signals."""
    tracker = NodeTracker(state, "intent_router", event="route", path="control")
    topic_decision = check_topic_guardrail(state)
    if not topic_decision.allowed:
        decision = guardrail_intent_decision(topic_decision)
        security_updates = security_event_updates(
            {**state, "intent_decision": decision},
            node="intent_router",
            decision=topic_decision,
        )
        return tracker.finish(
            {
                **security_updates,
                "intent_decision": decision,
                "fallback_reason": topic_decision.reason,
                "final_answer": state.get("final_answer") or f"Fallback: {topic_decision.reason}",
            },
            summary=safe_summary(topic_decision.reason, max_chars=120),
            status="failed",
            error_type="GuardrailViolation",
        )

    decision = state.get("intent_decision") or route_intent(state)
    return tracker.finish(
        {"intent_decision": decision},
        summary=(
            f"path={decision['path']} confidence={decision['confidence']:.2f} "
            f"reason={safe_summary(decision['reason'], max_chars=120)}"
        ),
    )


def choose_execution_path(state: AgentState) -> Literal[
    "direct_answer",
    "react_agent",
    "planner",
    "multi_agent_orchestrator",
    "fallback",
]:
    """Select the next runnable path from the router decision."""
    decision = state.get("intent_decision")
    if not decision:
        return "fallback"
    return decision["path"]


async def fallback(state: AgentState) -> AgentState:
    """Fallback placeholder for later routing and safety tasks."""
    tracker = NodeTracker(state, "fallback", event="fallback")
    decision = state.get("intent_decision")
    evaluation = state.get("evaluation") or {
        "enabled": False,
        "status": "not_required",
        "issues": [],
        "suggestions": [],
    }
    reason = (
        state.get("fallback_reason")
        or (
            "Reflection failed after maximum revision rounds."
            if evaluation.get("status") == "fail"
            else None
        )
        or (decision["reason"] if decision else None)
        or "Fallback path selected."
    )
    partial = state.get("final_answer")
    issues = evaluation.get("issues", [])
    if evaluation.get("status") == "fail" and partial:
        final_answer = (
            f"{partial}\n\nFallback: quality review did not pass after "
            f"{state.get('reflection_round', 0)} revision round(s). Issues: "
            f"{'; '.join(issues) or 'unspecified'}."
        )
    else:
        final_answer = partial or f"Fallback: {reason}"
    updates: AgentState = {
        "fallback_reason": reason,
        "final_answer": final_answer,
    }
    if evaluation.get("status") == "fail":
        updates["reflection_exhausted"] = True
    return tracker.finish(
        updates,
        summary=f"fallback_reason={safe_summary(reason, max_chars=160)}",
        status="completed",
    )


async def final_answer(state: AgentState) -> AgentState:
    """Ensure the graph always returns a final answer field."""
    tracker = NodeTracker(state, "final_answer", path="control")
    answer = (
        state.get("final_answer")
        or "SuperAgent runtime skeleton completed without a generated answer."
    )
    return tracker.finish(
        {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)],
        },
        summary=f"final_answer_chars={len(answer)}",
    )


def create_graph_builder(
    llm_client: LLMClient | None = None,
    mcp_client: MCPClient | None = None,
    worker_registry: object | None = None,
    evaluator: object | None = None,
    reviser: object | None = None,
    memory_client: LongTermMemoryClient | None = None,
) -> StateGraph[AgentState]:
    """Create the SuperAgent graph builder without external connections."""
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("intake", intake)
    graph_builder.add_node("load_memory", create_load_memory_node(client=memory_client))
    graph_builder.add_node("context_budget", context_budget)
    graph_builder.add_node("compress_memory", compress_memory)
    graph_builder.add_node("intent_router", intent_router)
    graph_builder.add_node("direct_answer", create_direct_answer_node(llm_client))
    graph_builder.add_node(
        "react_agent",
        create_react_node(llm_client=llm_client, mcp_client=mcp_client),
    )
    graph_builder.add_node("plan_generate", create_plan_generate_node())
    graph_builder.add_node("plan_validate", create_plan_validate_node())
    resolved_worker_registry = _resolve_worker_registry(worker_registry, llm_client)
    graph_builder.add_node(
        "execute_plan",
        create_execute_plan_node(
            llm_client=llm_client,
            mcp_client=mcp_client,
            worker_registry=resolved_worker_registry,
        ),
    )
    graph_builder.add_node("step_observe", create_step_observe_node())
    orchestrator_node = create_multi_agent_orchestrator_node(
        registry=resolved_worker_registry,
    )
    graph_builder.add_node("multi_agent_orchestrator", orchestrator_node)
    graph_builder.add_node("fallback", fallback)
    graph_builder.add_node("reflection_gate", create_reflection_gate_node())
    graph_builder.add_node(
        "evaluator",
        create_evaluator_node(
            evaluator if callable(evaluator) else None,
            llm_client=llm_client,
        ),
    )
    graph_builder.add_node(
        "revise",
        create_revise_node(reviser if callable(reviser) else None),
    )
    graph_builder.add_node(
        "memory_write",
        create_memory_write_node(client=memory_client),
    )
    graph_builder.add_node("final_answer", final_answer)

    graph_builder.add_edge("__start__", "intake")
    graph_builder.add_edge("intake", "load_memory")
    graph_builder.add_edge("load_memory", "context_budget")
    graph_builder.add_conditional_edges(
        "context_budget",
        choose_context_budget_path,
        {"compress_memory": "compress_memory", "ok": "intent_router"},
    )
    graph_builder.add_edge("compress_memory", "intent_router")
    graph_builder.add_conditional_edges(
        "intent_router",
        choose_execution_path,
        {
            "direct_answer": "direct_answer",
            "react_agent": "react_agent",
            "planner": "plan_generate",
            "multi_agent_orchestrator": "multi_agent_orchestrator",
            "fallback": "fallback",
        },
    )
    graph_builder.add_conditional_edges(
        "plan_validate",
        choose_plan_validate_path,
        {"execute_plan": "execute_plan", "fallback": "fallback"},
    )
    graph_builder.add_edge("plan_generate", "plan_validate")
    graph_builder.add_edge("execute_plan", "step_observe")
    graph_builder.add_conditional_edges(
        "step_observe",
        choose_plan_execution_path,
        {"execute_plan": "execute_plan", "memory_write": "reflection_gate"},
    )
    graph_builder.add_edge("direct_answer", "reflection_gate")
    graph_builder.add_edge("react_agent", "reflection_gate")
    graph_builder.add_edge("multi_agent_orchestrator", "reflection_gate")
    graph_builder.add_edge("fallback", "reflection_gate")
    graph_builder.add_conditional_edges(
        "reflection_gate",
        choose_reflection_path,
        {"evaluator": "evaluator", "memory_write": "memory_write"},
    )
    graph_builder.add_conditional_edges(
        "evaluator",
        choose_evaluator_path,
        {"memory_write": "memory_write", "revise": "revise", "fallback": "fallback"},
    )
    graph_builder.add_edge("revise", "reflection_gate")
    graph_builder.add_edge("memory_write", "final_answer")
    graph_builder.add_edge("final_answer", END)
    return graph_builder


def _resolve_worker_registry(
    worker_registry: object | None,
    llm_client: LLMClient | None,
) -> WorkerRegistry | None:
    if isinstance(worker_registry, WorkerRegistry):
        return worker_registry
    if llm_client is not None:
        return create_production_worker_registry(llm_client=llm_client)
    return None


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    llm_client: LLMClient | None = None,
    mcp_client: MCPClient | None = None,
    worker_registry: object | None = None,
    evaluator: object | None = None,
    reviser: object | None = None,
    memory_client: LongTermMemoryClient | None = None,
):
    """Compile the graph, optionally with a checkpointer."""
    return create_graph_builder(
        llm_client,
        mcp_client,
        worker_registry,
        evaluator,
        reviser,
        memory_client,
    ).compile(
        checkpointer=checkpointer,
        name="SuperAgent Runtime Skeleton",
    )


async def create_graph_with_checkpointer() -> tuple[object, CheckpointerResource]:
    """Create a compiled graph with PostgreSQL checkpointer fallback."""
    resource = await create_postgres_checkpointer()
    return build_graph(checkpointer=resource.checkpointer), resource


graph = build_graph()
