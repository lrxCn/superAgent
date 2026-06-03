"""Direct-answer runtime path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent.llm import LLMClient, LLMProviderError, LLMRequest, create_siliconflow_llm
from agent.state import AgentState, Evaluation, MemoryContext, Message, Plan

SYSTEM_PROMPT = (
    "You are SuperAgent's direct answer path. Answer the user's request directly "
    "when it is low-risk and does not need tools or planning. Respect the user's "
    "language, constraints, and requested format. Do not claim to have used tools."
)


@dataclass
class DirectAnswerNode:
    """Generate final answers for simple routed requests."""

    llm_factory: Callable[[], LLMClient] = create_siliconflow_llm

    async def __call__(self, state: AgentState) -> AgentState:
        """Generate a direct final answer or record a fallback reason."""
        evaluation: Evaluation = {
            "enabled": bool(
                state.get("intent_decision", {}).get("requires_reflection", False)
            ),
            "status": "not_required",
            "issues": [],
            "suggestions": [],
        }
        plan: Plan = {"steps": [], "status": "not_started"}
        try:
            llm = self.llm_factory()
            result = await llm.generate(
                LLMRequest(messages=build_direct_answer_messages(state), temperature=0.2)
            )
        except Exception as exc:
            if isinstance(exc, LLMProviderError):
                reason = str(exc)
            else:
                reason = f"Direct answer LLM call failed: {exc}"
            return {
                "fallback_reason": reason,
                "evaluation": state.get("evaluation") or evaluation,
                "plan": state.get("plan") or plan,
                "current_step": state.get("current_step"),
                "final_answer": state.get("final_answer") or f"Fallback: {reason}",
            }

        return {
            "final_answer": state.get("final_answer") or result.content.strip(),
            "evaluation": state.get("evaluation") or evaluation,
            "plan": state.get("plan") or plan,
            "current_step": state.get("current_step"),
        }


def build_direct_answer_messages(state: AgentState) -> list[Message]:
    """Build the compact prompt input consumed by the direct-answer LLM."""
    user_goal = _latest_user_text(state)
    memory_context = state.get("memory_context") or _empty_memory_context()
    budget = state.get("context_budget")
    context_summary = budget["summary"] if budget else None
    context_lines = [
        f"Current user goal:\n{user_goal}",
        _format_memory_context(memory_context),
    ]
    if context_summary:
        context_lines.append(f"Compressed context summary:\n{context_summary}")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(context_lines)},
    ]


def create_direct_answer_node(
    llm_client: LLMClient | None = None,
) -> DirectAnswerNode:
    """Create a direct-answer node with an optional test LLM client."""
    if llm_client is None:
        return DirectAnswerNode()
    return DirectAnswerNode(llm_factory=lambda: llm_client)


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if message["role"] == "user":
            return message["content"]
    return ""


def _empty_memory_context() -> MemoryContext:
    return {"short_term": [], "long_term": [], "entities": [], "errors": []}


def _format_memory_context(memory_context: MemoryContext) -> str:
    sections = [
        ("Short-term memory", memory_context.get("short_term", [])),
        ("Long-term memory", memory_context.get("long_term", [])),
        ("Entities", memory_context.get("entities", [])),
        ("Memory errors", memory_context.get("errors", [])),
    ]
    lines = ["Relevant memory context:"]
    for label, values in sections:
        rendered = "; ".join(values) if values else "none"
        lines.append(f"- {label}: {rendered}")
    return "\n".join(lines)
