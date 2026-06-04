"""Observability schema, safe summaries, and path metrics tests."""

from __future__ import annotations

from agent.observability import (
    append_runtime_event,
    build_path_metrics,
    build_runtime_event,
    langsmith_tracing_enabled,
    safe_summary,
    safe_tool_summary,
)
from agent.state import AgentState, RuntimeEvent


def test_safe_summary_redacts_secrets_and_truncates() -> None:
    secret = "api_key=super-secret-value " + ("x" * 400)
    rendered = safe_summary(secret, max_chars=80)
    assert "super-secret-value" not in rendered
    assert "[redacted]" in rendered
    assert len(rendered) <= 80


def test_safe_tool_summary_records_keys_not_values() -> None:
    summary = safe_tool_summary(
        "read_file",
        {"path": "/tmp/README.md", "api_key": "hidden"},
        status="completed",
    )
    assert "read_file" in summary
    assert "arg_keys=" in summary
    assert "hidden" not in summary
    assert "sensitive_args=redacted" in summary


def test_runtime_event_fields_are_structured() -> None:
    event = build_runtime_event(
        event="node",
        node="direct_answer",
        status="completed",
        summary="answer ready",
        path="direct_answer",
        duration_ms=12,
    )
    assert event["event"] == "node"
    assert event["path"] == "direct_answer"
    assert event["node"] == "direct_answer"
    assert event["status"] == "completed"
    assert event["duration_ms"] == 12
    assert event["summary"] == "answer ready"


def test_security_runtime_event_is_structured() -> None:
    event = build_runtime_event(
        event="security",
        node="react_agent",
        status="failed",
        summary="Guardrail blocked tool",
        path="react_agent",
        error_type="GuardrailViolation",
    )

    assert event["event"] == "security"
    assert event["status"] == "failed"
    assert event["error_type"] == "GuardrailViolation"


def test_path_metrics_aggregate_active_path() -> None:
    state: AgentState = {
        "intent_decision": {
            "path": "react_agent",
            "reason": "tools",
            "confidence": 0.9,
            "signals": ["tool"],
            "requires_reflection": True,
        }
    }
    events: list[RuntimeEvent] = []
    for node in ("intake", "react_agent"):
        events, _ = append_runtime_event(
            {**state, "runtime_events": events},
            build_runtime_event(
                event="node",
                node=node,
                status="completed",
                summary=node,
                path="react_agent" if node != "intake" else "control",
                duration_ms=5,
            ),
        )
    metrics = build_path_metrics(events, "react_agent")
    assert metrics["path"] == "react_agent"
    assert metrics["event_count"] == 1
    assert metrics["nodes"] == ["react_agent"]
    assert metrics["total_duration_ms"] == 5


def test_langsmith_tracing_requires_api_key() -> None:
    assert langsmith_tracing_enabled(
        type(
            "Cfg",
            (),
            {"langchain_tracing_v2": True, "langsmith_api_key_present": False},
        )()
    ) is False
    assert langsmith_tracing_enabled(
        type(
            "Cfg",
            (),
            {"langchain_tracing_v2": True, "langsmith_api_key_present": True},
        )()
    ) is True
