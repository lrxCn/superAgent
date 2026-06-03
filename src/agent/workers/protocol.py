"""Worker input/output contracts for multi-agent orchestration."""

from __future__ import annotations

from typing import Awaitable, Callable, Literal

from typing_extensions import TypedDict

from agent.state import AgentResult

WorkerRole = Literal["researcher", "coder", "reviewer", "memory_manager"]
WorkerStatus = Literal["completed", "failed", "skipped"]
WorkerAggregateStatus = Literal["completed", "partial", "failed"]

ROLE_AGENT_NAMES: dict[WorkerRole, str] = {
    "researcher": "researcher_agent",
    "coder": "coder_agent",
    "reviewer": "reviewer_agent",
    "memory_manager": "memory_manager_agent",
}


class WorkerInput(TypedDict):
    """Normalized input passed to each Worker."""

    role: WorkerRole
    task: str
    context: str


class WorkerOutput(TypedDict):
    """Result produced by a single Worker execution."""

    role: WorkerRole
    status: WorkerStatus
    result: str
    error: str | None
    confidence: float


WorkerCallable = Callable[[WorkerInput], Awaitable[WorkerOutput]]


def worker_output_to_agent_result(output: WorkerOutput) -> AgentResult:
    """Map a worker output into graph ``agent_results`` entries."""
    agent_status: Literal["completed", "failed", "skipped"]
    if output["status"] == "completed":
        agent_status = "completed"
    elif output["status"] == "skipped":
        agent_status = "skipped"
    else:
        agent_status = "failed"

    result: AgentResult = {
        "agent_name": ROLE_AGENT_NAMES[output["role"]],
        "status": agent_status,
        "output": output["result"],
        "confidence": output["confidence"],
        "role": output["role"],
    }
    if output.get("error"):
        result["error"] = output["error"]
    return result
