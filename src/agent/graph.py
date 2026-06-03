"""LangGraph skeleton for the SuperAgent runtime."""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from agent.config import load_config
from agent.context_budget import check_context_budget, compress_state_context
from agent.llm import LLMClient
from agent.memory.checkpoint import CheckpointerResource, create_postgres_checkpointer
from agent.nodes.direct import create_direct_answer_node
from agent.router import route_intent
from agent.state import (
    AgentResult,
    AgentState,
    MemoryContext,
    MemoryWriteResult,
    Observation,
    Plan,
    RuntimeConfig,
)


def _runtime_config(state: AgentState) -> RuntimeConfig:
    return state.get("runtime_config") or load_config().to_runtime_config()


async def intake(state: AgentState) -> AgentState:
    """Normalize caller input into the shared runtime state."""
    return {
        "runtime_config": _runtime_config(state),
        "tool_calls": state.get("tool_calls", []),
        "observations": state.get("observations", []),
        "agent_results": state.get("agent_results", []),
        "mcp_sessions": state.get("mcp_sessions", []),
        "fallback_reason": state.get("fallback_reason"),
    }


async def load_memory(state: AgentState) -> AgentState:
    """Load placeholder memory context."""
    memory_context: MemoryContext = {
        "short_term": [],
        "long_term": [],
        "entities": [],
        "errors": [],
    }
    return {"memory_context": state.get("memory_context") or memory_context}


async def context_budget(state: AgentState) -> AgentState:
    """Estimate context budget before routing."""
    budget = check_context_budget(state, limit=load_config().llm_max_tokens)
    return {"context_budget": budget}


def choose_context_budget_path(state: AgentState) -> Literal["compress_memory", "ok"]:
    """Route over-budget state through deterministic compression."""
    budget = state.get("context_budget")
    if budget and budget["estimated"] > budget["limit"]:
        return "compress_memory"
    return "ok"


async def compress_memory(state: AgentState) -> AgentState:
    """Compress context deterministically without calling an LLM."""
    budget = state.get("context_budget")
    limit = budget["limit"] if budget else load_config().llm_max_tokens
    return compress_state_context(state, limit=limit)


async def intent_router(state: AgentState) -> AgentState:
    """Choose an execution path from structured intent signals."""
    decision = route_intent(state)
    return {"intent_decision": state.get("intent_decision") or decision}


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


async def react_agent(state: AgentState) -> AgentState:
    """Tool path placeholder until the MCP/ReAct task implements execution."""
    observation: Observation = {
        "source": "react_agent",
        "content": "ReAct tool path selected by intent router.",
        "error": None,
    }
    return {
        "observations": [*state.get("observations", []), observation],
        "final_answer": state.get("final_answer")
        or "ReAct agent path selected; tool execution is not implemented yet.",
    }


async def planner(state: AgentState) -> AgentState:
    """Planner path placeholder until plan-and-execute is implemented."""
    plan: Plan = {"steps": [], "status": "pending"}
    return {
        "plan": state.get("plan") or plan,
        "final_answer": state.get("final_answer")
        or "Planner path selected; plan execution is not implemented yet.",
    }


async def multi_agent_orchestrator(state: AgentState) -> AgentState:
    """Multi-agent path placeholder until worker orchestration is implemented."""
    result: AgentResult = {
        "agent_name": "orchestrator",
        "status": "skipped",
        "output": "Multi-agent path selected by intent router.",
        "confidence": state.get("intent_decision", {}).get("confidence", 0.0),
    }
    return {
        "agent_results": [*state.get("agent_results", []), result],
        "final_answer": state.get("final_answer")
        or "Multi-agent path selected; worker orchestration is not implemented yet.",
    }


async def fallback(state: AgentState) -> AgentState:
    """Fallback placeholder for later routing and safety tasks."""
    decision = state.get("intent_decision")
    reason = (
        state.get("fallback_reason")
        or (decision["reason"] if decision else None)
        or "Fallback path selected."
    )
    return {
        "fallback_reason": reason,
        "final_answer": state.get("final_answer") or f"Fallback: {reason}",
    }


async def memory_write(state: AgentState) -> AgentState:
    """Skip memory writes until memory tasks are implemented."""
    result: MemoryWriteResult = {
        "status": "skipped",
        "reason": "Memory write is not implemented in the skeleton.",
    }
    return {"memory_write_result": state.get("memory_write_result") or result}


async def final_answer(state: AgentState) -> AgentState:
    """Ensure the graph always returns a final answer field."""
    return {
        "final_answer": state.get("final_answer")
        or "SuperAgent runtime skeleton completed without a generated answer."
    }


def create_graph_builder(llm_client: LLMClient | None = None) -> StateGraph[AgentState]:
    """Create the SuperAgent graph builder without external connections."""
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("intake", intake)
    graph_builder.add_node("load_memory", load_memory)
    graph_builder.add_node("context_budget", context_budget)
    graph_builder.add_node("compress_memory", compress_memory)
    graph_builder.add_node("intent_router", intent_router)
    graph_builder.add_node("direct_answer", create_direct_answer_node(llm_client))
    graph_builder.add_node("react_agent", react_agent)
    graph_builder.add_node("planner", planner)
    graph_builder.add_node("multi_agent_orchestrator", multi_agent_orchestrator)
    graph_builder.add_node("fallback", fallback)
    graph_builder.add_node("memory_write", memory_write)
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
            "planner": "planner",
            "multi_agent_orchestrator": "multi_agent_orchestrator",
            "fallback": "fallback",
        },
    )
    graph_builder.add_edge("direct_answer", "memory_write")
    graph_builder.add_edge("react_agent", "memory_write")
    graph_builder.add_edge("planner", "memory_write")
    graph_builder.add_edge("multi_agent_orchestrator", "memory_write")
    graph_builder.add_edge("fallback", "memory_write")
    graph_builder.add_edge("memory_write", "final_answer")
    graph_builder.add_edge("final_answer", END)
    return graph_builder


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    llm_client: LLMClient | None = None,
):
    """Compile the graph, optionally with a checkpointer."""
    return create_graph_builder(llm_client).compile(
        checkpointer=checkpointer,
        name="SuperAgent Runtime Skeleton",
    )


async def create_graph_with_checkpointer() -> tuple[object, CheckpointerResource]:
    """Create a compiled graph with PostgreSQL checkpointer fallback."""
    resource = await create_postgres_checkpointer()
    return build_graph(checkpointer=resource.checkpointer), resource


graph = build_graph()
