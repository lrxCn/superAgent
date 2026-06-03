"""Runtime observability: structured events, path metrics, and safe summaries."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from agent.config import AppConfig, load_config
from agent.state import (
    AgentState,
    ObservedPath,
    PathMetrics,
    RuntimeEvent,
    RuntimeEventName,
    RuntimeEventStatus,
)

MAX_SUMMARY_CHARS = 240

_SENSITIVE_CONTENT_PATTERN = re.compile(
    r"(password|passwd|token|secret|api[_-]?key|authorization|credential|"
    r"private[_-]?key|access[_-]?key|bearer\s+[a-z0-9._-]{8,}|"
    r"sk-[a-z0-9]{8,}|"
    r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----|"
    r"密码|密钥|凭证|秘钥)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+"
)


def langsmith_tracing_enabled(config: AppConfig | None = None) -> bool:
    """Return whether LangSmith tracing should be active for this process."""
    cfg = config or load_config()
    return cfg.langchain_tracing_v2 and cfg.langsmith_api_key_present


def safe_summary(value: object, *, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Render a short summary without leaking secrets or long payloads."""
    if value is None:
        return ""
    if isinstance(value, str):
        rendered = _redact_sensitive_text(value)
    elif isinstance(value, dict):
        rendered = json.dumps(_redact_sensitive_value(value), ensure_ascii=False, default=str)
    elif isinstance(value, list):
        rendered = json.dumps(
            [_redact_sensitive_value(item) for item in value],
            ensure_ascii=False,
            default=str,
        )
    else:
        rendered = _redact_sensitive_text(str(value))
    return _truncate_text(rendered, max_chars=max_chars)


def safe_tool_summary(
    tool_name: str,
    arguments: dict[str, object] | None = None,
    *,
    status: str | None = None,
    error: str | None = None,
) -> str:
    """Summarize a tool invocation without recording full arguments."""
    parts = [f"tool={tool_name}"]
    if status:
        parts.append(f"status={status}")
    if arguments:
        keys = sorted(str(key) for key in arguments.keys())
        parts.append(f"arg_keys={','.join(keys[:8])}")
        if any(_SENSITIVE_CONTENT_PATTERN.search(str(key)) for key in keys):
            parts.append("sensitive_args=redacted")
    if error:
        parts.append(f"error={safe_summary(error, max_chars=80)}")
    return _truncate_text("; ".join(parts), max_chars=MAX_SUMMARY_CHARS)


def resolve_execution_path(state: AgentState) -> ObservedPath:
    """Resolve the active route path from router output."""
    decision = state.get("intent_decision")
    if decision and decision.get("path"):
        return decision["path"]
    return "unknown"


def build_runtime_event(
    *,
    event: RuntimeEventName,
    node: str,
    status: RuntimeEventStatus,
    summary: str,
    path: ObservedPath | None = None,
    duration_ms: int = 0,
    error_type: str | None = None,
    state: AgentState | None = None,
) -> RuntimeEvent:
    """Create one structured runtime event."""
    resolved_path = path if path is not None else (
        resolve_execution_path(state) if state is not None else "unknown"
    )
    payload: RuntimeEvent = {
        "event": event,
        "path": resolved_path,
        "node": node,
        "status": status,
        "duration_ms": max(0, duration_ms),
        "summary": safe_summary(summary),
    }
    if error_type is not None:
        payload["error_type"] = error_type
    return payload


def append_runtime_event(
    state: AgentState,
    event: RuntimeEvent,
) -> tuple[list[RuntimeEvent], PathMetrics]:
    """Append an event and recompute path metrics."""
    events = [*state.get("runtime_events", []), event]
    return events, build_path_metrics(events, resolve_execution_path(state))


def build_path_metrics(
    events: list[RuntimeEvent],
    path: ObservedPath | None = None,
) -> PathMetrics:
    """Aggregate node-level metrics for the active path."""
    resolved_path = path or "unknown"
    path_events = [event for event in events if event.get("path") == resolved_path]
    if not path_events and events:
        path_events = events
        resolved_path = events[-1].get("path", "unknown")

    nodes = [str(event["node"]) for event in path_events if event.get("node")]
    total_duration = sum(int(event.get("duration_ms", 0)) for event in path_events)
    terminal_status = path_events[-1]["status"] if path_events else None
    metrics: PathMetrics = {
        "path": resolved_path,
        "event_count": len(path_events),
        "nodes": nodes,
        "total_duration_ms": total_duration,
    }
    if terminal_status is not None:
        metrics["terminal_status"] = terminal_status
    return metrics


def observability_updates(
    state: AgentState,
    *,
    event: RuntimeEventName,
    node: str,
    status: RuntimeEventStatus,
    summary: str,
    duration_ms: int = 0,
    error_type: str | None = None,
    path: ObservedPath | None = None,
) -> AgentState:
    """Return state updates containing a new runtime event and metrics."""
    runtime_event = build_runtime_event(
        event=event,
        node=node,
        status=status,
        summary=summary,
        duration_ms=duration_ms,
        error_type=error_type,
        path=path,
        state=state,
    )
    events, metrics = append_runtime_event(state, runtime_event)
    return {"runtime_events": events, "path_metrics": metrics}


@dataclass
class NodeTracker:
    """Measure one node execution and emit a structured completion event."""

    state: AgentState
    node: str
    event: RuntimeEventName = "node"
    path: ObservedPath | None = None
    _started_at: float = field(default_factory=time.perf_counter)

    def finish(
        self,
        updates: AgentState | None = None,
        *,
        summary: str,
        status: RuntimeEventStatus = "completed",
        error_type: str | None = None,
    ) -> AgentState:
        """Merge node updates with observability fields."""
        duration_ms = int((time.perf_counter() - self._started_at) * 1000)
        base_state: AgentState = {**self.state, **(updates or {})}
        observation = observability_updates(
            base_state,
            event=self.event,
            node=self.node,
            status=status,
            summary=summary,
            duration_ms=duration_ms,
            error_type=error_type,
            path=self.path,
        )
        if not updates:
            return observation
        merged: AgentState = {**updates, **observation}
        return merged


def _truncate_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = "... [truncated]"
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def _redact_sensitive_text(text: str) -> str:
    redacted = _SENSITIVE_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    if _SENSITIVE_CONTENT_PATTERN.search(redacted):
        return "[redacted]"
    return redacted


def _redact_sensitive_value(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SENSITIVE_CONTENT_PATTERN.search(key_text):
                sanitized[key_text] = "[redacted]"
            else:
                sanitized[key_text] = _redact_sensitive_value(item)
        return sanitized
    if isinstance(value, list):
        return [_redact_sensitive_value(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value
