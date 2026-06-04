"""Tenant identity contract tests."""

from __future__ import annotations

import pytest

from agent.graph import build_graph
from agent.identity import graphiti_group_id, resolve_runtime_identity
from agent.llm import FakeLLMClient
from agent.memory.graphiti import MockLongTermMemoryClient
from agent.state import AgentState

pytestmark = pytest.mark.anyio


def test_runtime_identity_prefers_langgraph_configurable() -> None:
    state: AgentState = {
        "thread_id": "state-thread",
        "user_id": "state-user",
        "group_id": "state-group",
    }

    identity = resolve_runtime_identity(
        state,
        {
            "configurable": {
                "thread_id": "config-thread",
                "user_id": "config-user",
                "group_id": "config-group",
            }
        },
    )

    assert identity.thread_id == "config-thread"
    assert identity.user_id == "config-user"
    assert identity.group_id == graphiti_group_id("config-group")


def test_runtime_identity_user_config_resets_group_default() -> None:
    identity = resolve_runtime_identity(
        {"group_id": "state-group"},
        {"configurable": {"user_id": "config-user"}},
    )

    assert identity.user_id == "config-user"
    assert identity.group_id == graphiti_group_id("config-user")


def test_runtime_identity_defaults_group_id_to_user_id() -> None:
    identity = resolve_runtime_identity(
        {},
        {"configurable": {"user_id": "tenant-a"}},
    )

    assert identity.user_id == "tenant-a"
    assert identity.group_id == graphiti_group_id("tenant-a")
    assert identity.thread_id is None


def test_graphiti_group_id_is_safe_and_stable() -> None:
    first = graphiti_group_id("tenant-a@example.com")
    second = graphiti_group_id("tenant-a@example.com")

    assert first == second
    assert first.startswith("tenant_a_example_com_")
    assert "-" not in first
    assert "@" not in first


async def test_graph_intake_copies_thread_and_user_from_configurable() -> None:
    client = MockLongTermMemoryClient()
    graph = build_graph(
        llm_client=FakeLLMClient(responses=["tenant answer"]),
        memory_client=client,
    )

    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "hello"}]},
        config={
            "configurable": {
                "thread_id": "thread-a",
                "user_id": "tenant-a",
            }
        },
    )

    assert result["thread_id"] == "thread-a"
    assert result["user_id"] == "tenant-a"
    assert result["group_id"] == graphiti_group_id("tenant-a")


async def test_graph_memory_does_not_cross_tenant_group_ids() -> None:
    client = MockLongTermMemoryClient()
    graph = build_graph(
        llm_client=FakeLLMClient(
            responses=[
                "Stored tenant A marker.",
                "Stored tenant B marker.",
                "Tenant A read.",
                "Tenant B read.",
            ]
        ),
        memory_client=client,
    )

    await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "preference: tenant-shared-marker belongs to tenant A",
                }
            ]
        },
        config={"configurable": {"thread_id": "thread-a1", "user_id": "tenant-a"}},
    )
    await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "preference: tenant-shared-marker belongs to tenant B",
                }
            ]
        },
        config={"configurable": {"thread_id": "thread-b1", "user_id": "tenant-b"}},
    )

    read_a = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "tenant-shared-marker"}]},
        config={"configurable": {"thread_id": "thread-a2", "user_id": "tenant-a"}},
    )
    read_b = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "tenant-shared-marker"}]},
        config={"configurable": {"thread_id": "thread-b2", "user_id": "tenant-b"}},
    )

    assert read_a["memory_context"]["long_term"] == [
        "preference: tenant-shared-marker belongs to tenant A"
    ]
    assert read_b["memory_context"]["long_term"] == [
        "preference: tenant-shared-marker belongs to tenant B"
    ]
