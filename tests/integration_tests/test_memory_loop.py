from __future__ import annotations

import os
from asyncio import sleep
from uuid import uuid4

import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.memory.graphiti import create_graphiti_client

pytestmark = [pytest.mark.anyio, pytest.mark.graphiti]


async def test_graph_memory_write_is_read_by_new_thread() -> None:
    if os.environ.get("RUN_GRAPHITI_TESTS") != "true":
        pytest.skip("Set RUN_GRAPHITI_TESTS=true after local Graphiti is running.")

    client = create_graphiti_client()
    if not await client.health():
        pytest.skip("Graphiti service is not reachable.")

    marker = f"loopmark-{uuid4().hex[:12]}"
    write_thread_id = f"memory-loop-write-{uuid4()}"
    read_thread_id = f"memory-loop-read-{uuid4()}"
    graph = build_graph(
        llm_client=FakeLLMClient(
            responses=[
                "Stored the memory loop marker.",
                "Read the memory loop marker.",
            ]
        ),
        memory_client=client,
    )

    write_result = await graph.ainvoke(
        {
            "thread_id": write_thread_id,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "preference: For memory loop checks, use "
                        f"{marker} as the marker."
                    ),
                }
            ],
        },
        config={"configurable": {"thread_id": write_thread_id}},
    )

    assert write_result["memory_write_result"]["status"] == "stored"

    read_result = await _invoke_until_memory_visible(
        graph=graph,
        marker=marker,
        thread_id=read_thread_id,
    )

    assert read_result["memory_context"]["errors"] == []
    assert any(marker in item for item in read_result["memory_context"]["long_term"])


async def test_graphiti_memory_loop_isolated_by_tenant_group() -> None:
    if os.environ.get("RUN_GRAPHITI_TESTS") != "true":
        pytest.skip("Set RUN_GRAPHITI_TESTS=true after local Graphiti is running.")

    client = create_graphiti_client()
    if not await client.health():
        pytest.skip("Graphiti service is not reachable.")

    marker = f"tenant-loopmark-{uuid4().hex[:12]}"
    tenant_a = f"tenant-a-{uuid4().hex[:8]}"
    tenant_b = f"tenant-b-{uuid4().hex[:8]}"
    graph = build_graph(
        llm_client=FakeLLMClient(
            responses=[
                "Stored tenant A memory.",
                "Stored tenant B memory.",
                "Read tenant A memory.",
                "Read tenant B memory.",
            ]
        ),
        memory_client=client,
    )

    await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"preference: {marker} belongs to tenant A",
                }
            ],
        },
        config={
            "configurable": {
                "thread_id": f"tenant-a-write-{uuid4()}",
                "user_id": tenant_a,
            }
        },
    )
    await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"preference: {marker} belongs to tenant B",
                }
            ],
        },
        config={
            "configurable": {
                "thread_id": f"tenant-b-write-{uuid4()}",
                "user_id": tenant_b,
            }
        },
    )

    read_a = await _invoke_until_memory_visible(
        graph=graph,
        marker=marker,
        thread_id=f"tenant-a-read-{uuid4()}",
        user_id=tenant_a,
    )
    read_b = await _invoke_until_memory_visible(
        graph=graph,
        marker=marker,
        thread_id=f"tenant-b-read-{uuid4()}",
        user_id=tenant_b,
    )

    tenant_a_memory = "\n".join(read_a["memory_context"]["long_term"])
    tenant_b_memory = "\n".join(read_b["memory_context"]["long_term"])
    assert "tenant A" in tenant_a_memory
    assert "tenant B" not in tenant_a_memory
    assert "tenant B" in tenant_b_memory
    assert "tenant A" not in tenant_b_memory


async def _invoke_until_memory_visible(
    *,
    graph: object,
    marker: str,
    thread_id: str,
    user_id: str = "main",
    attempts: int = 18,
    delay_seconds: float = 5.0,
) -> dict[str, object]:
    result: dict[str, object] | None = None
    for attempt in range(attempts):
        result = await graph.ainvoke(
            {
                "thread_id": thread_id,
                "messages": [
                    {"role": "user", "content": f"What memory mentions {marker}?"}
                ],
            },
            config={"configurable": {"thread_id": thread_id, "user_id": user_id}},
        )
        memory_context = result["memory_context"]
        if any(marker in item for item in memory_context["long_term"]):
            return result
        if attempt < attempts - 1:
            await sleep(delay_seconds)
    assert result is not None
    return result
