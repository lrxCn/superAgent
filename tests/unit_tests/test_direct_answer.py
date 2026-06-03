import pytest

from agent.llm import FakeLLMClient, LLMProviderError, LLMRequest, LLMResult
from agent.nodes.direct import build_direct_answer_messages, create_direct_answer_node
from agent.state import AgentState

pytestmark = pytest.mark.anyio


def test_build_direct_answer_messages_include_goal_memory_and_summary() -> None:
    state: AgentState = {
        "messages": [{"role": "user", "content": "Explain LangGraph briefly."}],
        "memory_context": {
            "short_term": ["recent thread fact"],
            "long_term": ["prefers Chinese"],
            "entities": ["SuperAgent"],
            "errors": ["Graphiti unavailable"],
        },
        "context_budget": {
            "limit": 100,
            "estimated": 140,
            "compressed": True,
            "summary": "Older messages were compressed.",
            "dropped_messages": 2,
            "dropped_memories": 1,
        },
    }

    messages = build_direct_answer_messages(state)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert "Explain LangGraph briefly." in content
    assert "recent thread fact" in content
    assert "prefers Chinese" in content
    assert "SuperAgent" in content
    assert "Older messages were compressed." in content


async def test_direct_answer_node_writes_final_answer_with_fake_llm() -> None:
    llm = FakeLLMClient(responses=["LangGraph is a stateful graph runtime."])
    node = create_direct_answer_node(llm)

    result = await node({"messages": [{"role": "user", "content": "What is LangGraph?"}]})

    assert result["final_answer"] == "LangGraph is a stateful graph runtime."
    assert result["evaluation"]["enabled"] is False
    assert result["plan"]["status"] == "not_started"
    assert llm.calls[0].temperature == 0.2
    assert "What is LangGraph?" in llm.calls[0].messages[1]["content"]


async def test_direct_answer_node_records_fallback_when_llm_fails() -> None:
    class FailingLLM:
        async def generate(self, request: LLMRequest) -> LLMResult:
            raise LLMProviderError("provider unavailable")

    node = create_direct_answer_node(FailingLLM())

    result = await node({"messages": [{"role": "user", "content": "hello"}]})

    assert result["fallback_reason"] == "provider unavailable"
    assert result["final_answer"] == "Fallback: provider unavailable"
