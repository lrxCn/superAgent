import importlib

import pytest

from agent.context_budget import (
    check_context_budget,
    compress_state_context,
    estimate_state_tokens,
    estimate_tokens,
)
from agent.state import AgentState


def test_estimate_tokens_uses_deterministic_character_approximation() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_context_budget_normal_path_reports_usage_without_compression() -> None:
    state: AgentState = {
        "messages": [{"role": "user", "content": "small request"}],
        "memory_context": {
            "short_term": [],
            "long_term": [],
            "entities": [],
            "errors": [],
        },
    }

    budget = check_context_budget(state, limit=100)

    assert budget["limit"] == 100
    assert budget["estimated"] == estimate_state_tokens(state)
    assert budget["compressed"] is False
    assert budget["summary"] is None
    assert budget["dropped_messages"] == 0
    assert budget["dropped_memories"] == 0


def test_compression_preserves_current_goal_system_constraints_and_recent_messages() -> None:
    state: AgentState = {
        "messages": [
            {"role": "system", "content": "Hard constraint: answer in Chinese."},
            {"role": "user", "content": "old user context"},
            {"role": "assistant", "content": "old assistant context"},
            {"role": "user", "content": "recent goal context"},
            {"role": "assistant", "content": "recent assistant context"},
            {"role": "user", "content": "current goal: build the budget node"},
        ],
        "memory_context": {
            "short_term": [],
            "long_term": [],
            "entities": [],
            "errors": [],
        },
    }

    result = compress_state_context(state, limit=1, recent_message_count=2)
    kept_contents = [message["content"] for message in result["messages"]]

    assert "Hard constraint: answer in Chinese." in kept_contents
    assert "current goal: build the budget node" in kept_contents
    assert "recent assistant context" in kept_contents
    assert "old user context" not in kept_contents
    assert result["context_budget"]["compressed"] is True
    assert result["context_budget"]["dropped_messages"] == 3


def test_compression_keeps_high_value_memory_and_drops_low_value_memory() -> None:
    state: AgentState = {
        "messages": [{"role": "user", "content": "current task"}],
        "memory_context": {
            "short_term": [
                "low value scratch note",
                "High: user prefers concise Chinese replies",
            ],
            "long_term": [
                "Fact: project uses uv",
                "temporary unrelated note",
            ],
            "entities": ["SuperAgent project"],
            "errors": ["Graphiti unavailable"],
        },
    }

    result = compress_state_context(state, limit=1)
    memory_context = result["memory_context"]

    assert memory_context["short_term"] == [
        "High: user prefers concise Chinese replies"
    ]
    assert memory_context["long_term"] == ["Fact: project uses uv"]
    assert memory_context["entities"] == ["SuperAgent project"]
    assert memory_context["errors"] == ["Graphiti unavailable"]
    assert result["context_budget"]["dropped_memories"] == 2


@pytest.mark.anyio
async def test_graph_compresses_over_budget_context_before_routing(monkeypatch) -> None:
    class SmallBudgetConfig:
        llm_max_tokens = 12

        def to_runtime_config(self):
            return {
                "react_max_steps": 8,
                "plan_max_steps": 12,
                "worker_max_concurrency": 4,
                "worker_timeout_seconds": 120,
                "tool_timeout_seconds": 30,
                "reflection_max_rounds": 1,
                "memory_enabled": True,
                "reflection_enabled": True,
            }

    graph_module = importlib.import_module("agent.graph")
    monkeypatch.setattr(graph_module, "load_config", lambda: SmallBudgetConfig())
    graph = graph_module.build_graph()
    result = await graph.ainvoke(
        {
            "messages": [
                {"role": "system", "content": "Hard constraint: keep constraints."},
                {"role": "user", "content": "old context " * 80},
                {"role": "assistant", "content": "old answer " * 80},
                {"role": "user", "content": "current goal must survive"},
            ],
            "memory_context": {
                "short_term": ["discard me", "High: preserve this memory"],
                "long_term": ["discard long memory"],
                "entities": [],
                "errors": [],
            },
        }
    )

    assert result["context_budget"]["compressed"] is True
    assert result["context_budget"]["limit"] == 12
    assert result["memory_context"]["short_term"] == ["High: preserve this memory"]
    assert result["messages"][-1]["content"] == "current goal must survive"
    assert result["final_answer"] == (
        "SuperAgent runtime skeleton received: current goal must survive"
    )
