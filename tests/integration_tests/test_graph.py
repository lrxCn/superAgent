import pytest

from agent import graph

pytestmark = pytest.mark.anyio


async def test_agent_simple_passthrough() -> None:
    inputs = {"messages": [{"role": "user", "content": "some request"}]}
    res = await graph.ainvoke(inputs)
    assert res["intent_decision"]["path"] == "direct_answer"
    assert res["memory_write_result"]["status"] == "skipped"
    assert res["final_answer"] == "SuperAgent runtime skeleton received: some request"
    assert "changeme" not in res
