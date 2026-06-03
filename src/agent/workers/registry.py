"""Worker registry for orchestrator dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.workers.protocol import WorkerCallable, WorkerRole


@dataclass
class WorkerRegistry:
    """Role-to-callable registry consumed by the orchestrator."""

    workers: dict[WorkerRole, WorkerCallable] = field(default_factory=dict)

    def get(self, role: WorkerRole) -> WorkerCallable | None:
        """Return the worker callable registered for ``role``."""
        return self.workers.get(role)
