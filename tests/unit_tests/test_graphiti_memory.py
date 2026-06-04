import json

import httpx
import pytest

from agent.config import load_config
from agent.memory.graphiti import (
    GraphitiMemoryClient,
    MemoryRecord,
    MemoryWrite,
    MockLongTermMemoryClient,
    create_graphiti_client,
)


@pytest.mark.anyio
async def test_mock_graphiti_client_reads_and_writes_memory() -> None:
    client = MockLongTermMemoryClient()

    write_result = await client.write(
        MemoryWrite(
            content="User prefers concise Chinese answers.",
            source="unit-test",
        )
    )
    search_result = await client.search("concise")

    assert write_result.status == "stored"
    assert len(search_result.records) == 1
    assert search_result.records[0].source == "unit-test"


@pytest.mark.anyio
async def test_mock_graphiti_client_reports_read_write_failures() -> None:
    client = MockLongTermMemoryClient(
        records=[MemoryRecord(content="existing fact")],
        write_error="write disabled",
        search_error="service unavailable",
    )

    write_result = await client.write(MemoryWrite(content="new fact", source="test"))
    search_result = await client.search("fact")

    assert write_result.status == "skipped"
    assert write_result.error == "write disabled"
    assert search_result.records == []
    assert search_result.error == "service unavailable"


def test_create_graphiti_client_uses_config_defaults() -> None:
    client = create_graphiti_client(load_config({}))

    assert client.backend == "falkordb"
    assert client.base_url == "http://localhost:8000"


@pytest.mark.anyio
async def test_graphiti_health_falls_back_when_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GraphitiMemoryClient(
            base_url="http://graphiti.local",
            http_client=http_client,
        )
        assert await client.health() is False


@pytest.mark.anyio
async def test_graphiti_search_and_write_use_mcp_tools() -> None:
    seen_payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "unit-test",
                "result": {"content": [{"name": "fact", "summary": "known fact"}]},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GraphitiMemoryClient(
            base_url="http://graphiti.local",
            http_client=http_client,
        )
        search_result = await client.search("known")
        write_result = await client.write(MemoryWrite(content="known fact", source="test"))

    assert len(search_result.records) == 1
    assert write_result.status == "stored"
    assert seen_payloads[0]["params"]["name"] == "search_nodes"
    assert seen_payloads[1]["params"]["name"] == "add_memory"
