"""LangGraph skeleton for the SuperAgent runtime."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph

from agent.config import load_config
from agent.state import (
    AgentState,
    ContextBudget,
    Evaluation,
    IntentDecision,
    MemoryContext,
    MemoryWriteResult,
    Plan,
    RuntimeConfig,
)


def _runtime_config(state: AgentState) -> RuntimeConfig:
    return state.get("runtime_config") or load_config().to_runtime_config()


def _message_text(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    return messages[-1]["content"]


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
    """Estimate placeholder context budget."""
    message_chars = sum(len(message["content"]) for message in state.get("messages", []))
    budget: ContextBudget = {
        "estimated_tokens": max(1, message_chars // 4) if message_chars else 0,
        "max_tokens": load_config().llm_max_tokens,
        "compressed": False,
        "summary": None,
    }
    return {"context_budget": state.get("context_budget") or budget}


async def intent_router(state: AgentState) -> AgentState:
    """Route the initial skeleton to the direct path."""
    decision: IntentDecision = {
        "path": "direct_answer",
        "reason": "Skeleton router defaults to direct_answer until routing is implemented.",
        "confidence": 1.0,
    }
    return {"intent_decision": state.get("intent_decision") or decision}


def choose_execution_path(state: AgentState) -> Literal["direct_answer", "fallback"]:
    """Select the next runnable path for the skeleton graph."""
    decision = state.get("intent_decision")
    if decision and decision["path"] == "fallback":
        return "fallback"
    return "direct_answer"


async def direct_answer(state: AgentState) -> AgentState:
    """Direct-answer placeholder without calling an LLM."""
    user_text = _message_text(state)
    answer = (
        "SuperAgent runtime skeleton received the request."
        if not user_text
        else f"SuperAgent runtime skeleton received: {user_text}"
    )
    evaluation: Evaluation = {
        "enabled": False,
        "status": "not_required",
        "issues": [],
        "suggestions": [],
    }
    plan: Plan = {"steps": [], "status": "not_started"}
    return {
        "final_answer": state.get("final_answer", answer),
        "evaluation": state.get("evaluation") or evaluation,
        "plan": state.get("plan") or plan,
        "current_step": state.get("current_step"),
    }


async def fallback(state: AgentState) -> AgentState:
    """Fallback placeholder for later routing and safety tasks."""
    reason = state.get("fallback_reason") or "Skeleton fallback path selected."
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


graph_builder = StateGraph(AgentState)
graph_builder.add_node("intake", intake)
graph_builder.add_node("load_memory", load_memory)
graph_builder.add_node("context_budget", context_budget)
graph_builder.add_node("intent_router", intent_router)
graph_builder.add_node("direct_answer", direct_answer)
graph_builder.add_node("fallback", fallback)
graph_builder.add_node("memory_write", memory_write)
graph_builder.add_node("final_answer", final_answer)

graph_builder.add_edge("__start__", "intake")
graph_builder.add_edge("intake", "load_memory")
graph_builder.add_edge("load_memory", "context_budget")
graph_builder.add_edge("context_budget", "intent_router")
graph_builder.add_conditional_edges(
    "intent_router",
    choose_execution_path,
    {"direct_answer": "direct_answer", "fallback": "fallback"},
)
graph_builder.add_edge("direct_answer", "memory_write")
graph_builder.add_edge("fallback", "memory_write")
graph_builder.add_edge("memory_write", "final_answer")
graph_builder.add_edge("final_answer", END)

graph = graph_builder.compile(name="SuperAgent Runtime Skeleton")
