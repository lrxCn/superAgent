"""Memory write node coordinating Graphiti long-term writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from agent.config import load_config
from agent.identity import resolve_runtime_identity
from agent.memory.graphiti import (
    LongTermMemoryClient,
    MemoryWrite,
    create_graphiti_client,
)
from agent.memory.policy import MemoryWriteCandidate, evaluate_write_policies
from agent.observability import NodeTracker, safe_summary
from agent.state import AgentState, Evaluation, MemoryWriteResult


class MemoryClientFactory(Protocol):
    """Factory protocol for injecting long-term memory clients."""

    def __call__(self) -> LongTermMemoryClient:
        """Create a long-term memory client."""


@dataclass
class MemoryWriteNode:
    """Write stable long-term memories without blocking final answer."""

    client_factory: MemoryClientFactory = create_graphiti_client

    async def __call__(self, state: AgentState) -> AgentState:
        """Execute memory write policies and record structured results."""
        tracker = NodeTracker(state, "memory_write", event="memory_write")
        result = await execute_memory_write(state, client=self.client_factory())
        status = result["status"]
        return tracker.finish(
            {"memory_write_result": result},
            summary=(
                f"memory_write status={status} target={result['target']} "
                f"reason={safe_summary(result.get('reason') or '', max_chars=120)}"
            ),
            status="completed" if status in {"stored", "skipped"} else "failed",
            error_type="MemoryWriteError" if status == "error" else None,
        )


async def execute_memory_write(
    state: AgentState,
    *,
    client: LongTermMemoryClient,
) -> MemoryWriteResult:
    """Apply policies and write eligible candidates to Graphiti."""
    policy_result = evaluate_write_policies(state)
    if policy_result.candidates == [] and policy_result.skipped:
        first_skip = policy_result.skipped[0]
        if first_skip in {
            "memory_disabled",
            "evaluation_failed",
            "reflection_exhausted_unreliable",
            "fallback_unreliable",
        }:
            return _skipped_result(first_skip)
        if policy_result.skipped:
            return _skipped_result(
                "no_eligible_candidates",
                extra_reason="; ".join(policy_result.skipped[:3]),
            )

    if not policy_result.candidates:
        return _skipped_result("no_eligible_candidates")

    stored_count = 0
    errors: list[str] = []
    identity = resolve_runtime_identity(state)
    for candidate in policy_result.candidates:
        write_result = await client.write(
            _candidate_to_memory_write(candidate, state, group_id=identity.group_id)
        )
        if write_result.status == "stored":
            stored_count += 1
            continue
        if write_result.error:
            errors.append(write_result.error)

    if stored_count > 0:
        return {
            "status": "stored",
            "target": "graphiti",
            "reason": f"stored {stored_count} long-term memory item(s)",
            "error": errors[0] if errors else None,
            "stored_count": stored_count,
        }

    if errors:
        return {
            "status": "error",
            "target": "graphiti",
            "reason": "graphiti_write_failed",
            "error": errors[0],
            "stored_count": 0,
        }

    return _skipped_result("no_eligible_candidates")


def _candidate_to_memory_write(
    candidate: MemoryWriteCandidate,
    state: AgentState,
    *,
    group_id: str,
) -> MemoryWrite:
    evaluation: Evaluation = state.get("evaluation") or {
        "enabled": False,
        "status": "not_required",
        "issues": [],
        "suggestions": [],
    }
    decision = state.get("intent_decision")
    metadata = {
        **candidate.metadata,
        "category": candidate.category,
        "confidence": candidate.confidence,
        "evaluation_status": evaluation.get("status", "not_required"),
        "path": decision["path"] if decision else None,
        "user_id": state.get("user_id"),
        "group_id": group_id,
    }
    return MemoryWrite(
        content=candidate.content,
        source=candidate.source,
        group_id=group_id,
        metadata=metadata,
        timestamp=datetime.now(UTC).isoformat(),
    )


def _skipped_result(reason: str, *, extra_reason: str | None = None) -> MemoryWriteResult:
    combined = f"{reason}: {extra_reason}" if extra_reason else reason
    return {
        "status": "skipped",
        "target": "none",
        "reason": combined,
        "error": None,
        "stored_count": 0,
    }


def create_memory_write_node(
    client: LongTermMemoryClient | None = None,
    client_factory: MemoryClientFactory | None = None,
) -> MemoryWriteNode:
    """Create the memory write graph node."""
    if client is not None:
        return MemoryWriteNode(client_factory=lambda: client)
    if client_factory is not None:
        return MemoryWriteNode(client_factory=client_factory)
    return MemoryWriteNode(client_factory=_default_client_factory)


def _default_client_factory() -> LongTermMemoryClient:
    return create_graphiti_client(load_config())
