"""Tenant and thread identity helpers."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.config import DEFAULT_USER_ID, load_config
from agent.state import AgentState

_GRAPHITI_GROUP_ID_PATTERN = re.compile(r"[^A-Za-z0-9_]+")
_MAX_GROUP_ID_LENGTH = 72


@dataclass(frozen=True)
class RuntimeIdentity:
    """Resolved identifiers shared by checkpoint, memory, and tracing."""

    user_id: str
    group_id: str
    thread_id: str | None = None


def resolve_runtime_identity(
    state: AgentState,
    config: RunnableConfig | Mapping[str, Any] | None = None,
    *,
    default_user_id: str | None = None,
) -> RuntimeIdentity:
    """Resolve user/thread identity from LangGraph config and state.

    LangGraph checkpointers read ``configurable.thread_id`` directly. Runtime
    nodes mirror that value into state so memory and observability can share the
    same contract.
    """
    configurable = _mapping(config, "configurable")
    metadata = _mapping(config, "metadata")
    fallback_user_id = default_user_id or load_config().default_user_id or DEFAULT_USER_ID

    user_id = (
        _first_text(
            configurable.get("user_id"),
            state.get("user_id"),
            metadata.get("user_id"),
            fallback_user_id,
        )
        or DEFAULT_USER_ID
    )
    config_group_id = _first_text(configurable.get("group_id"), metadata.get("group_id"))
    state_group_id = _first_text(state.get("group_id"))
    group_id = (
        config_group_id
        or (user_id if configurable.get("user_id") else state_group_id)
        or user_id
    )
    thread_id = _first_text(
        configurable.get("thread_id"),
        state.get("thread_id"),
        metadata.get("thread_id"),
    )
    return RuntimeIdentity(
        user_id=user_id,
        group_id=graphiti_group_id(group_id),
        thread_id=thread_id,
    )


def graphiti_group_id(value: str) -> str:
    """Return a deterministic Graphiti-safe group id.

    FalkorDB/RediSearch treats some punctuation as query syntax when Graphiti
    later filters by group. Keep the caller's ``user_id`` unchanged and only
    normalize the Graphiti boundary identifier.
    """
    raw = value.strip() or DEFAULT_USER_ID
    normalized = _GRAPHITI_GROUP_ID_PATTERN.sub("_", raw).strip("_") or DEFAULT_USER_ID
    if normalized == raw and len(normalized) <= _MAX_GROUP_ID_LENGTH:
        return normalized
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    prefix = normalized[: max(1, _MAX_GROUP_ID_LENGTH - len(digest) - 1)].strip("_")
    return f"{prefix or DEFAULT_USER_ID}_{digest}"


def identity_state_updates(identity: RuntimeIdentity) -> AgentState:
    """Return state fields for a resolved runtime identity."""
    updates: AgentState = {
        "user_id": identity.user_id,
        "group_id": identity.group_id,
    }
    if identity.thread_id:
        updates["thread_id"] = identity.thread_id
    return updates


def resolve_group_id(state: AgentState) -> str:
    """Return the Graphiti group_id for the current state."""
    return resolve_runtime_identity(state).group_id


def _mapping(
    config: RunnableConfig | Mapping[str, Any] | None,
    key: str,
) -> Mapping[str, Any]:
    if not isinstance(config, Mapping):
        return {}
    value = config.get(key)
    return value if isinstance(value, Mapping) else {}


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        elif value is not None:
            normalized = str(value).strip()
            if normalized:
                return normalized
    return None
