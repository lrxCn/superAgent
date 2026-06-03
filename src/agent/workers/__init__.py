"""Worker agents for parallel multi-agent orchestration."""

from agent.workers.mock import (
    MockWorkerBehavior,
    create_mock_worker_registry,
)
from agent.workers.protocol import (
    WorkerAggregateStatus,
    WorkerInput,
    WorkerOutput,
    WorkerRole,
    worker_output_to_agent_result,
)
from agent.workers.registry import WorkerRegistry


def default_worker_registry() -> WorkerRegistry:
    """Production skeleton registry backed by mock workers."""
    return create_mock_worker_registry()

__all__ = [
    "MockWorkerBehavior",
    "WorkerAggregateStatus",
    "WorkerInput",
    "WorkerOutput",
    "WorkerRegistry",
    "WorkerRole",
    "create_mock_worker_registry",
    "default_worker_registry",
    "worker_output_to_agent_result",
]
