import os

import pytest

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
