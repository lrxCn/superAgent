import os

import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.memory.graphiti import MemoryWrite, create_graphiti_client

pytestmark = [pytest.mark.anyio, pytest.mark.graphiti]


async def test_graphiti_client_smoke() -> None:
    if os.environ.get("RUN_GRAPHITI_TESTS") != "true":
        pytest.skip("Set RUN_GRAPHITI_TESTS=true after local Graphiti is running.")

    client = create_graphiti_client()
    if not await client.health():
        pytest.skip("Graphiti service is not reachable.")

    write_result = await client.write(
        MemoryWrite(content="SuperAgent graphiti smoke test", source="integration-test")
    )
    assert write_result.status == "stored"

    search_result = await client.search("SuperAgent graphiti smoke test")
    assert search_result.error is None


async def test_load_memory_reads_graphiti_long_term_context() -> None:
    if os.environ.get("RUN_GRAPHITI_TESTS") != "true":
        pytest.skip("Set RUN_GRAPHITI_TESTS=true after local Graphiti is running.")

    client = create_graphiti_client()
    if not await client.health():
        pytest.skip("Graphiti service is not reachable.")

    memory_text = "SuperAgent load_memory integration fact"
    write_result = await client.write(
        MemoryWrite(content=memory_text, source="load-memory-integration-test")
    )
    assert write_result.status == "stored"

    graph = build_graph(
        llm_client=FakeLLMClient(responses=["load memory answer"]),
        memory_client=client,
    )
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": memory_text}]}
    )

    assert result["memory_context"]["errors"] == []
    assert result["memory_context"]["long_term"]
