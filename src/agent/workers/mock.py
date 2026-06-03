"""Mock workers with deterministic fake behavior for tests and skeleton runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agent.workers.protocol import WorkerCallable, WorkerInput, WorkerOutput, WorkerRole
from agent.workers.registry import WorkerRegistry

MOCK_OUTPUTS: dict[WorkerRole, str] = {
    "researcher": "Research summary: gathered references and key facts for the task.",
    "coder": "Coder output: proposed implementation outline and test checklist.",
    "reviewer": "Review notes: risks, gaps, and quality checks for the deliverable.",
    "memory_manager": "Memory candidates: durable facts and preferences worth storing later.",
}


@dataclass(frozen=True)
class MockWorkerBehavior:
    """Per-role mock behavior used in unit tests."""

    delay_seconds: float = 0.0
    raise_error: str | None = None
    confidence: float = 0.85


def _build_mock_worker(
    role: WorkerRole,
    behavior: MockWorkerBehavior | None = None,
) -> WorkerCallable:
    resolved = behavior or MockWorkerBehavior()

    async def _run(worker_input: WorkerInput) -> WorkerOutput:
        if resolved.delay_seconds > 0:
            await asyncio.sleep(resolved.delay_seconds)
        if resolved.raise_error:
            raise RuntimeError(resolved.raise_error)
        return {
            "role": role,
            "status": "completed",
            "result": MOCK_OUTPUTS[role],
            "error": None,
            "confidence": resolved.confidence,
        }

    return _run


def create_mock_worker_registry(
    behaviors: dict[WorkerRole, MockWorkerBehavior] | None = None,
) -> WorkerRegistry:
    """Create a registry of mock workers, optionally overriding per-role behavior."""
    overrides = behaviors or {}
    workers: dict[WorkerRole, WorkerCallable] = {}
    for role in MOCK_OUTPUTS:
        workers[role] = _build_mock_worker(role, overrides.get(role))
    return WorkerRegistry(workers=workers)
