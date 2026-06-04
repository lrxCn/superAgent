"""Configurable runtime guardrails for topics and tool calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.config import load_config
from agent.observability import observability_updates, safe_summary
from agent.state import (
    AgentState,
    IntentDecision,
    RuntimeConfig,
    is_user_message,
    message_content_text,
)


@dataclass(frozen=True)
class GuardrailConfig:
    """Per-run guardrail controls."""

    tool_allowlist: tuple[str, ...] = ()
    blocked_topics: tuple[str, ...] = ()
    max_tool_calls_per_run: int = 0


@dataclass(frozen=True)
class GuardrailDecision:
    """Result of a guardrail policy check."""

    allowed: bool
    rule: str
    reason: str
    tool_name: str | None = None
    matched_value: str | None = None


def guardrail_config_from_state(state: AgentState) -> GuardrailConfig:
    """Resolve guardrail config from graph state or process defaults."""
    runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
    return guardrail_config_from_runtime(runtime_config)


def guardrail_config_from_runtime(runtime_config: RuntimeConfig) -> GuardrailConfig:
    """Normalize guardrail-related runtime config fields."""
    return GuardrailConfig(
        tool_allowlist=tuple(
            _normalize_items(runtime_config.get("guardrail_tool_allowlist", []))
        ),
        blocked_topics=tuple(
            _normalize_items(runtime_config.get("guardrail_blocked_topics", []))
        ),
        max_tool_calls_per_run=max(
            0,
            int(runtime_config.get("max_tool_calls_per_run", 0) or 0),
        ),
    )


def check_topic_guardrail(state: AgentState) -> GuardrailDecision:
    """Block user requests that match configured topic deny terms."""
    config = guardrail_config_from_state(state)
    if not config.blocked_topics:
        return GuardrailDecision(
            allowed=True,
            rule="topic_block",
            reason="No blocked topics configured.",
        )

    text = _latest_user_text(state)
    for topic in config.blocked_topics:
        if _matches_text(text, topic):
            return GuardrailDecision(
                allowed=False,
                rule="topic_block",
                reason=f"Guardrail blocked topic '{topic}'.",
                matched_value=topic,
            )
    return GuardrailDecision(
        allowed=True,
        rule="topic_block",
        reason="No blocked topics matched.",
    )


def check_tool_guardrail(
    state: AgentState,
    *,
    tool_name: str,
    current_tool_call_count: int,
) -> GuardrailDecision:
    """Validate a planned tool call against allowlist and run-level limits."""
    config = guardrail_config_from_state(state)
    if config.tool_allowlist and not any(
        _tool_name_matches(pattern, tool_name)
        for pattern in config.tool_allowlist
    ):
        allowed = ", ".join(config.tool_allowlist)
        return GuardrailDecision(
            allowed=False,
            rule="tool_allowlist",
            reason=f"Guardrail blocked tool '{tool_name}'; allowed tools: {allowed}.",
            tool_name=tool_name,
        )

    if (
        config.max_tool_calls_per_run > 0
        and current_tool_call_count >= config.max_tool_calls_per_run
    ):
        return GuardrailDecision(
            allowed=False,
            rule="max_tool_calls_per_run",
            reason=(
                f"Guardrail blocked tool '{tool_name}'; max_tool_calls_per_run="
                f"{config.max_tool_calls_per_run} was reached."
            ),
            tool_name=tool_name,
            matched_value=str(config.max_tool_calls_per_run),
        )

    return GuardrailDecision(
        allowed=True,
        rule="tool_call",
        reason="Tool call allowed by guardrails.",
        tool_name=tool_name,
    )


def guardrail_intent_decision(decision: GuardrailDecision) -> IntentDecision:
    """Represent a blocked topic as a fallback route decision."""
    return {
        "path": "fallback",
        "reason": decision.reason,
        "confidence": 1.0,
        "signals": [f"guardrail:{decision.rule}"],
        "requires_reflection": True,
    }


def security_event_updates(
    state: AgentState,
    *,
    node: str,
    decision: GuardrailDecision,
) -> AgentState:
    """Append a structured security event for a guardrail violation."""
    parts = [f"guardrail_violation rule={decision.rule}"]
    if decision.tool_name:
        parts.append(f"tool={safe_summary(decision.tool_name, max_chars=80)}")
    if decision.matched_value:
        parts.append(f"matched={safe_summary(decision.matched_value, max_chars=80)}")
    return observability_updates(
        state,
        event="security",
        node=node,
        status="failed",
        summary="; ".join(parts),
        error_type="GuardrailViolation",
    )


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if is_user_message(message):
            return message_content_text(message)
    return ""


def _normalize_items(items: object) -> list[str]:
    if not isinstance(items, list | tuple):
        return []
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _matches_text(text: str, pattern: str) -> bool:
    normalized_text = text.lower()
    normalized_pattern = pattern.lower()
    if normalized_pattern.isascii() and re.search(r"[a-z0-9]", normalized_pattern):
        regex = rf"(?<![a-z0-9]){re.escape(normalized_pattern)}[a-z0-9_-]*(?![a-z0-9])"
        return re.search(regex, normalized_text) is not None
    return normalized_pattern in normalized_text


def _tool_name_matches(pattern: str, tool_name: str) -> bool:
    normalized_pattern = pattern.lower()
    normalized_tool = tool_name.lower()
    if normalized_pattern == normalized_tool:
        return True
    if normalized_pattern.endswith(".*"):
        return normalized_tool.startswith(normalized_pattern[:-1])
    if "." not in normalized_pattern:
        return normalized_tool.endswith(f".{normalized_pattern}")
    return False
