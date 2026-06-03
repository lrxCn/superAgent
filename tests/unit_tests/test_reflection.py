"""Reflection gate, evaluator, revise, and graph routing tests."""

from __future__ import annotations

import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.reflection import (
    EvaluationResult,
    compute_reflection_gate,
    evaluate_output,
    revise_output,
)
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
        "messages": [{"role": "user", "content": "What is LangGraph?"}],
        "runtime_config": _runtime_config(),
        "intent_decision": {
            "path": "direct_answer",
            "reason": "simple",
            "confidence": 0.82,
            "signals": ["simple_question"],
            "requires_reflection": False,
        },
        "final_answer": "LangGraph is a stateful graph runtime for agents.",
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_gate_skips_direct_low_risk_path_with_reason() -> None:
    gate = compute_reflection_gate(_state())

    assert gate.enabled is False
    assert gate.skip_reason == "direct_low_risk"
    assert gate.reasons == []


def test_gate_enables_for_tool_path_with_reason() -> None:
    gate = compute_reflection_gate(
        _state(
            intent_decision={
                "path": "react_agent",
                "reason": "tools",
                "confidence": 0.9,
                "signals": ["tool:file"],
                "requires_reflection": True,
            }
        )
    )

    assert gate.enabled is True
    assert "path:react_agent" in gate.reasons


def test_gate_enables_for_low_confidence_route() -> None:
    gate = compute_reflection_gate(
        _state(
            intent_decision={
                "path": "direct_answer",
                "reason": "ambiguous",
                "confidence": 0.65,
                "signals": ["ambiguous_direct"],
                "requires_reflection": True,
            }
        )
    )

    assert gate.enabled is True
    assert any(reason.startswith("low_confidence:") for reason in gate.reasons)


def test_gate_enables_for_high_risk_and_user_review() -> None:
    high_risk = compute_reflection_gate(
        _state(
            messages=[{"role": "user", "content": "Give legal advice on this contract."}],
            intent_decision={
                "path": "direct_answer",
                "reason": "simple",
                "confidence": 0.82,
                "signals": ["simple_question"],
                "requires_reflection": True,
            },
        )
    )
    review = compute_reflection_gate(
        _state(
            messages=[{"role": "user", "content": "Please review this answer carefully."}],
            intent_decision={
                "path": "direct_answer",
                "reason": "simple",
                "confidence": 0.82,
                "signals": ["simple_question"],
                "requires_reflection": True,
            },
        )
    )

    assert high_risk.enabled is True
    assert any(reason.startswith("high_risk:") for reason in high_risk.reasons)
    assert review.enabled is True
    assert any(reason.startswith("user_review:") for reason in review.reasons)


def test_gate_enables_before_fallback_path() -> None:
    gate = compute_reflection_gate(
        _state(
            messages=[{"role": "user", "content": "help"}],
            intent_decision={
                "path": "fallback",
                "reason": "underspecified",
                "confidence": 0.9,
                "signals": ["input_insufficient"],
                "requires_reflection": True,
            },
            final_answer="Fallback: Input is underspecified and needs clarification before execution.",
        )
    )

    assert gate.enabled is True
    assert "path:fallback" in gate.reasons


def test_evaluator_passes_clean_answer() -> None:
    result = evaluate_output(_state())

    assert result["status"] == "pass"
    assert result["requires_revision"] is False
    assert result["issues"] == []


def test_evaluator_fails_on_quality_marker() -> None:
    result = evaluate_output(_state(final_answer="NEEDS_REVISION draft"))

    assert result["status"] == "fail"
    assert result["requires_revision"] is True
    assert "quality_marker" in result["issues"]
    assert result["suggestions"]


def test_revise_removes_quality_marker() -> None:
    revised = revise_output(
        _state(
            final_answer="NEEDS_REVISION draft",
            evaluation={
                "enabled": True,
                "status": "fail",
                "issues": ["quality_marker"],
                "suggestions": ["Remove placeholder markers and answer the user directly."],
            },
        )
    )

    assert "NEEDS_REVISION" not in revised
    assert revised


async def test_direct_path_skips_evaluator_in_graph() -> None:
    graph = build_graph(llm_client=FakeLLMClient(responses=["LangGraph coordinates agent nodes."]))
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "What is LangGraph?"}]})

    assert result["intent_decision"]["path"] == "direct_answer"
    assert result["evaluation"]["enabled"] is False
    assert result["evaluation"]["skip_reason"] == "direct_low_risk"
    assert result["evaluation"]["status"] == "not_required"
    assert result.get("reflection_round", 0) == 0


async def test_tool_path_runs_evaluator_and_passes() -> None:
    graph = build_graph(
        llm_client=FakeLLMClient(
            responses=[
                '{"action":"finish","answer":"Tool path completed with enough detail."}',
            ]
        )
    )
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Read the README file and run the tests."}]}
    )

    assert result["intent_decision"]["path"] == "react_agent"
    assert result["evaluation"]["enabled"] is True
    assert result["evaluation"]["status"] == "pass"
    assert any(reason.startswith("path:react_agent") for reason in result["evaluation"]["gate_reasons"])


async def test_fail_revise_once_then_fallback_when_still_failing() -> None:
    def always_fail(_state: AgentState) -> EvaluationResult:
        return {
            "enabled": True,
            "status": "fail",
            "issues": ["forced_fail"],
            "suggestions": ["Try again with more detail."],
            "round": _state.get("reflection_round", 0),
            "requires_revision": True,
            "gate_reasons": ["test:forced_fail"],
            "skip_reason": None,
        }

    graph = build_graph(
        llm_client=FakeLLMClient(responses=["unused"]),
        evaluator=always_fail,
    )
    result = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Use researcher, coder, and reviewer agents in parallel.",
                }
            ]
        }
    )

    assert result["reflection_round"] == 1
    assert result["reflection_exhausted"] is True
    assert "Fallback: quality review did not pass" in result["final_answer"]
    assert result["fallback_reason"] == "Reflection failed after maximum revision rounds."
