"""Memory read node tests."""

from __future__ import annotations

import pytest

from agent.graph import build_graph
from agent.identity import graphiti_group_id
from agent.llm import FakeLLMClient
from agent.memory.graphiti import MemoryRecord, MockLongTermMemoryClient
from agent.memory.read import latest_user_query, load_memory_context
from agent.state import AgentState

pytestmark = pytest.mark.anyio


def _runtime_config(**overrides: object) -> dict[str, object]:
    base = {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }
    base.update(overrides)
    return base


def _state(**overrides: object) -> AgentState:
    state: AgentState = {
        "messages": [
            {"role": "user", "content": "older request"},
            {"role": "assistant", "content": "older answer"},
            {"role": "user", "content": "What is my preferred language?"},
        ],
        "runtime_config": _runtime_config(),
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_latest_user_query_uses_newest_user_message() -> None:
    assert latest_user_query(_state()["messages"]) == "What is my preferred language?"


async def test_load_memory_context_populates_long_term_from_graphiti() -> None:
    client = MockLongTermMemoryClient(
        records=[
            MemoryRecord(content="User prefers Chinese answers."),
            MemoryRecord(content="User prefers concise implementation notes."),
        ]
    )

    context = await load_memory_context(
        _state(messages=[{"role": "user", "content": "prefers"}]),
        client=client,
    )

    assert context["short_term"] == []
    assert context["long_term"] == [
        "User prefers Chinese answers.",
        "User prefers concise implementation notes.",
    ]
    assert context["errors"] == []


async def test_load_memory_context_preserves_existing_and_deduplicates() -> None:
    client = MockLongTermMemoryClient(
        records=[
            MemoryRecord(content="User prefers Chinese answers."),
            MemoryRecord(content="User prefers uv for Python projects."),
        ]
    )

    context = await load_memory_context(
        _state(
            messages=[{"role": "user", "content": "prefers"}],
            memory_context={
                "short_term": ["current thread summary"],
                "long_term": ["User prefers Chinese answers."],
                "entities": ["SuperAgent"],
                "errors": ["previous warning"],
            },
        ),
        client=client,
    )

    assert context["short_term"] == ["current thread summary"]
    assert context["long_term"] == [
        "User prefers Chinese answers.",
        "User prefers uv for Python projects.",
    ]
    assert context["entities"] == ["SuperAgent"]
    assert context["errors"] == ["previous warning"]


async def test_load_memory_context_empty_search_is_non_error() -> None:
    client = MockLongTermMemoryClient(records=[MemoryRecord(content="unrelated fact")])

    context = await load_memory_context(
        _state(messages=[{"role": "user", "content": "no match"}]),
        client=client,
    )

    assert context["long_term"] == []
    assert context["errors"] == []


async def test_load_memory_context_records_search_error_without_raising() -> None:
    client = MockLongTermMemoryClient(search_error="graphiti unavailable")

    context = await load_memory_context(_state(), client=client)

    assert context["long_term"] == []
    assert context["errors"] == ["Graphiti search failed: graphiti unavailable"]


async def test_load_memory_context_records_raised_search_error() -> None:
    class RaisingClient(MockLongTermMemoryClient):
        async def search(  # type: ignore[no-untyped-def]
            self,
            query: str,
            *,
            limit: int = 5,
            group_id: str | None = None,
        ):
            raise RuntimeError("connection refused")

    context = await load_memory_context(_state(), client=RaisingClient())

    assert context["long_term"] == []
    assert context["errors"] == ["Graphiti search failed: connection refused"]


async def test_load_memory_context_skips_when_memory_disabled() -> None:
    client = MockLongTermMemoryClient(records=[MemoryRecord(content="saved fact")])

    context = await load_memory_context(
        _state(runtime_config=_runtime_config(memory_enabled=False)),
        client=client,
    )

    assert context == {"short_term": [], "long_term": [], "entities": [], "errors": []}


async def test_load_memory_context_filters_by_group_id() -> None:
    client = MockLongTermMemoryClient(
        records=[
            MemoryRecord(
                content="Tenant A prefers marker-alpha.",
                metadata={"group_id": graphiti_group_id("tenant-a")},
            ),
            MemoryRecord(
                content="Tenant B prefers marker-alpha.",
                metadata={"group_id": graphiti_group_id("tenant-b")},
            ),
        ]
    )

    context = await load_memory_context(
        _state(
            user_id="tenant-a",
            group_id="tenant-a",
            messages=[{"role": "user", "content": "marker-alpha"}],
        ),
        client=client,
    )

    assert context["long_term"] == ["Tenant A prefers marker-alpha."]


async def test_graph_load_memory_uses_injected_client() -> None:
    client = MockLongTermMemoryClient(
        records=[MemoryRecord(content="User prefers Chinese answers.")]
    )
    graph = build_graph(
        llm_client=FakeLLMClient(responses=["direct fake answer"]),
        memory_client=client,
    )

    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "prefers"}]}
    )

    assert result["memory_context"]["long_term"] == ["User prefers Chinese answers."]
    assert result["final_answer"] == "direct fake answer"
