from agent.router import LOW_CONFIDENCE_THRESHOLD, route_intent
from agent.state import AgentState


def _state(text: str) -> AgentState:
    return {"messages": [{"role": "user", "content": text}]}


def test_routes_simple_question_to_direct_answer() -> None:
    decision = route_intent(_state("What is LangGraph?"))

    assert decision["path"] == "direct_answer"
    assert decision["confidence"] >= LOW_CONFIDENCE_THRESHOLD
    assert decision["signals"] == ["simple_question"]
    assert decision["requires_reflection"] is False


def test_routes_tool_request_to_react_agent() -> None:
    decision = route_intent(_state("Read the README file and run the tests."))

    assert decision["path"] == "react_agent"
    assert decision["confidence"] >= LOW_CONFIDENCE_THRESHOLD
    assert any(signal.startswith("tool:") for signal in decision["signals"])
    assert decision["requires_reflection"] is True


def test_routes_complex_implementation_request_to_planner() -> None:
    decision = route_intent(
        _state("Design and implement a migration plan, then validate each step.")
    )

    assert decision["path"] == "planner"
    assert any(signal.startswith("plan:") for signal in decision["signals"])
    assert decision["requires_reflection"] is True


def test_routes_parallel_specialist_request_to_multi_agent() -> None:
    decision = route_intent(
        _state("Use researcher, coder, and reviewer agents in parallel.")
    )

    assert decision["path"] == "multi_agent_orchestrator"
    assert any(signal.startswith("multi_agent:") for signal in decision["signals"])
    assert decision["requires_reflection"] is True


def test_routes_underspecified_input_to_fallback() -> None:
    decision = route_intent(_state("help"))

    assert decision["path"] == "fallback"
    assert "input_insufficient" in decision["signals"]
    assert decision["requires_reflection"] is True


def test_low_confidence_direct_request_requires_reflection() -> None:
    decision = route_intent(
        _state(
            "Summarize the tradeoffs across reliability, latency, observability, "
            "state ownership, memory freshness, evaluation quality, operator "
            "experience, and rollout sequencing for a runtime."
        )
    )

    assert decision["path"] == "direct_answer"
    assert decision["confidence"] < LOW_CONFIDENCE_THRESHOLD
    assert decision["requires_reflection"] is True
