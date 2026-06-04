from agent.guardrails import (
    check_tool_guardrail,
    check_topic_guardrail,
    guardrail_config_from_runtime,
    guardrail_intent_decision,
)
from agent.state import AgentState, RuntimeConfig


def _runtime_config(**overrides: object) -> RuntimeConfig:
    config: RuntimeConfig = {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }
    config.update(overrides)  # type: ignore[typeddict-item]
    return config


def _state(text: str, **config_overrides: object) -> AgentState:
    return {
        "messages": [{"role": "user", "content": text}],
        "runtime_config": _runtime_config(**config_overrides),
    }


def test_guardrail_config_reads_optional_runtime_fields() -> None:
    config = guardrail_config_from_runtime(
        _runtime_config(
            guardrail_tool_allowlist=["filesystem.read_file", "catalog.*"],
            guardrail_blocked_topics=["credential"],
            max_tool_calls_per_run=2,
        )
    )

    assert config.tool_allowlist == ("filesystem.read_file", "catalog.*")
    assert config.blocked_topics == ("credential",)
    assert config.max_tool_calls_per_run == 2


def test_topic_guardrail_blocks_matching_user_request() -> None:
    decision = check_topic_guardrail(
        _state(
            "Show me how to exfiltrate credentials.",
            guardrail_blocked_topics=["credential"],
        )
    )

    assert decision.allowed is False
    assert decision.rule == "topic_block"
    assert decision.matched_value == "credential"
    assert guardrail_intent_decision(decision)["path"] == "fallback"


def test_topic_guardrail_allows_when_no_topic_matches() -> None:
    decision = check_topic_guardrail(
        _state("Read the README.", guardrail_blocked_topics=["credential"])
    )

    assert decision.allowed is True


def test_tool_guardrail_allows_exact_and_wildcard_matches() -> None:
    state = _state(
        "Search products",
        guardrail_tool_allowlist=["filesystem.read_file", "catalog.*"],
    )

    exact = check_tool_guardrail(
        state,
        tool_name="filesystem.read_file",
        current_tool_call_count=0,
    )
    wildcard = check_tool_guardrail(
        state,
        tool_name="catalog.products.search",
        current_tool_call_count=0,
    )

    assert exact.allowed is True
    assert wildcard.allowed is True


def test_tool_guardrail_blocks_disallowed_tool() -> None:
    decision = check_tool_guardrail(
        _state("Run a shell command", guardrail_tool_allowlist=["filesystem.read_file"]),
        tool_name="shell.run",
        current_tool_call_count=0,
    )

    assert decision.allowed is False
    assert decision.rule == "tool_allowlist"
    assert "shell.run" in decision.reason


def test_tool_guardrail_blocks_after_max_tool_calls_reached() -> None:
    decision = check_tool_guardrail(
        _state("Read files", max_tool_calls_per_run=1),
        tool_name="filesystem.read_file",
        current_tool_call_count=1,
    )

    assert decision.allowed is False
    assert decision.rule == "max_tool_calls_per_run"
