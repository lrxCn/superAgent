"""Memory read node coordinating long-term Graphiti search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent.config import load_config
from agent.memory.graphiti import LongTermMemoryClient, create_graphiti_client
from agent.observability import NodeTracker, safe_summary
from agent.state import (
    AgentState,
    MemoryContext,
    Message,
    is_user_message,
    message_content_text,
)


class MemoryClientFactory(Protocol):
    """Factory protocol for injecting long-term memory clients."""

    def __call__(self) -> LongTermMemoryClient:
        """Create a long-term memory client."""


@dataclass
class LoadMemoryNode:
    """Read long-term memories without blocking graph execution."""

    client_factory: MemoryClientFactory = create_graphiti_client
    limit: int = 5

    async def __call__(self, state: AgentState) -> AgentState:
        """Load memory context from Graphiti search results."""
        tracker = NodeTracker(state, "load_memory", path="control")
        loaded = await load_memory_context(
            state,
            client=self.client_factory(),
            limit=self.limit,
        )
        error_type = None
        if loaded.get("errors"):
            error_type = "MemoryReadError"
        return tracker.finish(
            {"memory_context": loaded},
            summary=(
                f"memory_loaded short={len(loaded['short_term'])} "
                f"long={len(loaded['long_term'])} "
                f"errors={len(loaded['errors'])}"
            ),
            status="completed",
            error_type=error_type,
        )


async def load_memory_context(
    state: AgentState,
    *,
    client: LongTermMemoryClient,
    limit: int = 5,
) -> MemoryContext:
    """Read long-term memory for the latest user message."""
    context = normalize_memory_context(state.get("memory_context"))
    if not _memory_enabled(state):
        return context

    query = latest_user_query(state.get("messages", []))
    if not query:
        return context

    try:
        result = await client.search(query, limit=limit)
    except Exception as exc:
        context["errors"].append(f"Graphiti search failed: {safe_summary(exc)}")
        return context

    if result.error:
        context["errors"].append(f"Graphiti search failed: {safe_summary(result.error)}")
        return context

    existing = set(context["long_term"])
    for record in result.records[:limit]:
        content = record.content.strip()
        if content and content not in existing:
            context["long_term"].append(content)
            existing.add(content)
    return context


def normalize_memory_context(memory_context: MemoryContext | None) -> MemoryContext:
    """Return a complete memory context while preserving caller-provided items."""
    if not memory_context:
        return _empty_memory_context()
    return {
        "short_term": list(memory_context.get("short_term", [])),
        "long_term": list(memory_context.get("long_term", [])),
        "entities": list(memory_context.get("entities", [])),
        "errors": list(memory_context.get("errors", [])),
    }


def latest_user_query(messages: list[Message]) -> str:
    """Return the newest user message content for memory search."""
    for message in reversed(messages):
        if is_user_message(message):
            return message_content_text(message).strip()
    return ""


def create_load_memory_node(
    client: LongTermMemoryClient | None = None,
    client_factory: MemoryClientFactory | None = None,
) -> LoadMemoryNode:
    """Create the memory read graph node."""
    if client is not None:
        return LoadMemoryNode(client_factory=lambda: client)
    if client_factory is not None:
        return LoadMemoryNode(client_factory=client_factory)
    return LoadMemoryNode(client_factory=_default_client_factory)


def _memory_enabled(state: AgentState) -> bool:
    config = state.get("runtime_config")
    return config is None or config.get("memory_enabled", True)


def _empty_memory_context() -> MemoryContext:
    return {"short_term": [], "long_term": [], "entities": [], "errors": []}


def _default_client_factory() -> LongTermMemoryClient:
    return create_graphiti_client(load_config())
