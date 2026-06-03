import os

import pytest

from agent.config import load_config
from agent.graph import build_graph
from agent.memory.checkpoint import create_postgres_checkpointer

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]


async def test_postgres_checkpointer_can_persist_graph_state() -> None:
    if os.environ.get("RUN_POSTGRES_TESTS") != "true":
        pytest.skip("Set RUN_POSTGRES_TESTS=true to run PostgreSQL integration tests.")

    resource = await create_postgres_checkpointer(load_config())
    if resource.backend != "postgres":
        pytest.skip(resource.fallback_reason or "PostgreSQL checkpointer unavailable.")

    try:
        graph = build_graph(checkpointer=resource.checkpointer)
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "checkpoint test"}]},
            config={"configurable": {"thread_id": "postgres-checkpoint-test"}},
        )
        assert result["final_answer"] == (
            "SuperAgent runtime skeleton received: checkpoint test"
        )
    finally:
        await resource.aclose()
