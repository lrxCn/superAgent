"""Worker agents for parallel multi-agent orchestration."""

from agent.workers.mock import (
    MockWorkerBehavior,
    create_mock_worker_registry,
)
from agent.workers.production import (
    LLMWorker,
    build_worker_messages,
    create_production_worker_registry,
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
    """Production registry backed by role-specific LLM workers."""
    return create_production_worker_registry()


__all__ = [
    "LLMWorker",
    "MockWorkerBehavior",
    "WorkerAggregateStatus",
    "WorkerInput",
    "WorkerOutput",
    "WorkerRegistry",
    "WorkerRole",
    "build_worker_messages",
    "create_mock_worker_registry",
    "create_production_worker_registry",
    "default_worker_registry",
    "worker_output_to_agent_result",
]
