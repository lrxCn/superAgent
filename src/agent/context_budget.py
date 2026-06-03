"""Deterministic context budget estimation and compression."""

from __future__ import annotations

from agent.state import AgentState, ContextBudget, MemoryContext, Message

APPROX_CHARS_PER_TOKEN = 4
DEFAULT_RECENT_MESSAGE_COUNT = 4
HIGH_VALUE_MARKERS = (
    "high:",
    "important:",
    "priority:",
    "preference:",
    "constraint:",
    "fact:",
    "[high]",
    "[important]",
)


def estimate_tokens(text: str) -> int:
    """Estimate token usage without adding a tokenizer dependency."""
    if not text:
        return 0
    return max(1, (len(text) + APPROX_CHARS_PER_TOKEN - 1) // APPROX_CHARS_PER_TOKEN)


def estimate_state_tokens(state: AgentState) -> int:
    """Estimate context usage from messages, memory, tools, and observations."""
    total = 0
    for message in state.get("messages", []):
        total += estimate_tokens(f"{message['role']}: {message['content']}")

    memory_context = state.get("memory_context")
    if memory_context:
        total += _estimate_memory_context(memory_context)

    for tool_call in state.get("tool_calls", []):
        total += estimate_tokens(str(tool_call))
    for observation in state.get("observations", []):
        total += estimate_tokens(f"{observation['source']}: {observation['content']}")
    return total


def check_context_budget(state: AgentState, *, limit: int) -> ContextBudget:
    """Return a budget report without mutating state."""
    estimated = estimate_state_tokens(state)
    return {
        "limit": limit,
        "estimated": estimated,
        "compressed": False,
        "summary": None,
        "dropped_messages": 0,
        "dropped_memories": 0,
        "estimated_tokens": estimated,
        "max_tokens": limit,
    }


def compress_state_context(
    state: AgentState,
    *,
    limit: int,
    recent_message_count: int = DEFAULT_RECENT_MESSAGE_COUNT,
) -> AgentState:
    """Compress messages and memory context while preserving high-value inputs."""
    before = estimate_state_tokens(state)
    if before <= limit:
        return {"context_budget": check_context_budget(state, limit=limit)}

    messages = list(state.get("messages", []))
    memory_context = state.get("memory_context") or _empty_memory_context()
    kept_messages, dropped_messages = _compress_messages(
        messages,
        recent_message_count=recent_message_count,
    )
    kept_memory, dropped_memories = _compress_memory(memory_context)
    compressed_state: AgentState = {
        **state,
        "messages": kept_messages,
        "memory_context": kept_memory,
    }
    after = estimate_state_tokens(compressed_state)
    summary = _compression_summary(
        before=before,
        after=after,
        limit=limit,
        dropped_messages=dropped_messages,
        dropped_memories=dropped_memories,
    )
    budget: ContextBudget = {
        "limit": limit,
        "estimated": after,
        "compressed": True,
        "summary": summary,
        "dropped_messages": dropped_messages,
        "dropped_memories": dropped_memories,
        "estimated_tokens": after,
        "max_tokens": limit,
    }
    return {
        "messages": kept_messages,
        "memory_context": kept_memory,
        "context_budget": budget,
    }


def _estimate_memory_context(memory_context: MemoryContext) -> int:
    total = 0
    for item in memory_context.get("short_term", []):
        total += estimate_tokens(f"short_term: {item}")
    for item in memory_context.get("long_term", []):
        total += estimate_tokens(f"long_term: {item}")
    for item in memory_context.get("entities", []):
        total += estimate_tokens(f"entities: {item}")
    for item in memory_context.get("errors", []):
        total += estimate_tokens(f"errors: {item}")
    return total


def _compress_messages(
    messages: list[Message],
    *,
    recent_message_count: int,
) -> tuple[list[Message], int]:
    protected_indexes: set[int] = set()
    for index, message in enumerate(messages):
        if message["role"] == "system":
            protected_indexes.add(index)

    current_goal_index = _last_user_message_index(messages)
    if current_goal_index is not None:
        protected_indexes.add(current_goal_index)

    recent_start = max(0, len(messages) - recent_message_count)
    protected_indexes.update(range(recent_start, len(messages)))

    kept = [
        message for index, message in enumerate(messages) if index in protected_indexes
    ]
    return kept, len(messages) - len(kept)


def _last_user_message_index(messages: list[Message]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "user":
            return index
    return None


def _compress_memory(memory_context: MemoryContext) -> tuple[MemoryContext, int]:
    kept: MemoryContext = {
        "short_term": _high_value_items(memory_context.get("short_term", [])),
        "long_term": _high_value_items(memory_context.get("long_term", [])),
        "entities": list(memory_context.get("entities", [])),
        "errors": list(memory_context.get("errors", [])),
    }
    original_count = (
        len(memory_context.get("short_term", []))
        + len(memory_context.get("long_term", []))
        + len(memory_context.get("entities", []))
        + len(memory_context.get("errors", []))
    )
    kept_count = (
        len(kept["short_term"])
        + len(kept["long_term"])
        + len(kept["entities"])
        + len(kept["errors"])
    )
    return kept, original_count - kept_count


def _high_value_items(items: list[str]) -> list[str]:
    return [item for item in items if _is_high_value(item)]


def _is_high_value(item: str) -> bool:
    lowered = item.strip().lower()
    return lowered.startswith(HIGH_VALUE_MARKERS)


def _empty_memory_context() -> MemoryContext:
    return {"short_term": [], "long_term": [], "entities": [], "errors": []}


def _compression_summary(
    *,
    before: int,
    after: int,
    limit: int,
    dropped_messages: int,
    dropped_memories: int,
) -> str:
    return (
        "Deterministic context compression applied: "
        f"estimated {before}->{after}/{limit} tokens, "
        f"dropped {dropped_messages} messages and {dropped_memories} memory items."
    )
