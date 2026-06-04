"""Parallel multi-agent orchestrator node."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from agent.config import load_config
from agent.observability import NodeTracker
from agent.state import AgentResult, AgentState, Observation, RuntimeConfig
from agent.workers import default_worker_registry
from agent.workers.protocol import (
    ROLE_AGENT_NAMES,
    WorkerAggregateStatus,
    WorkerCallable,
    WorkerInput,
    WorkerOutput,
    WorkerRole,
    worker_output_to_agent_result,
)
from agent.workers.registry import WorkerRegistry

ROLE_KEYWORDS: dict[WorkerRole, tuple[str, ...]] = {
    "researcher": (
        "research",
        "researcher",
        "investigate",
        "gather",
        "资料",
        "研究",
        "检索",
        "调研",
    ),
    "coder": (
        "code",
        "coder",
        "implement",
        "develop",
        "refactor",
        "编码",
        "开发",
        "实现",
        "重构",
    ),
    "reviewer": (
        "review",
        "reviewer",
        "audit",
        "quality",
        "审查",
        "评审",
        "质检",
    ),
    "memory_manager": (
        "memory",
        "remember",
        "preference",
        "记忆",
        "偏好",
        "长期",
    ),
}

DEFAULT_WORKERS: tuple[WorkerRole, ...] = (
    "researcher",
    "coder",
    "reviewer",
)


def extract_user_task(state: AgentState) -> str:
    """Return the latest user message as the worker task."""
    for message in reversed(state.get("messages", [])):
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"]).strip()
    return ""


def select_worker_roles(state: AgentState) -> list[WorkerRole]:
    """Choose workers to run based on user text and router signals."""
    task = extract_user_task(state).lower()
    signals = " ".join(state.get("intent_decision", {}).get("signals", [])).lower()
    combined = f"{task} {signals}"
    selected = [
        role
        for role, keywords in ROLE_KEYWORDS.items()
        if any(keyword in combined for keyword in keywords)
    ]
    if selected:
        return selected
    return list(DEFAULT_WORKERS)


def build_worker_context(state: AgentState) -> str:
    """Serialize lightweight context for mock workers."""
    memory = state.get("memory_context")
    if not memory:
        return ""
    parts: list[str] = []
    if memory.get("short_term"):
        parts.append("short_term=" + "; ".join(memory["short_term"][:3]))
    if memory.get("long_term"):
        parts.append("long_term=" + "; ".join(memory["long_term"][:3]))
    return " | ".join(parts)


def aggregate_worker_outputs(
    outputs: list[WorkerOutput],
) -> tuple[WorkerAggregateStatus, float, str]:
    """Derive orchestrator status, confidence, and human-readable summary."""
    if not outputs:
        return "failed", 0.0, "No workers were selected for execution."

    completed = [item for item in outputs if item["status"] == "completed"]
    failed = [item for item in outputs if item["status"] == "failed"]
    skipped = [item for item in outputs if item["status"] == "skipped"]

    confidences = [item["confidence"] for item in outputs if item["status"] == "completed"]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    lines = [
        f"Multi-agent orchestration: {len(completed)} completed, "
        f"{len(failed)} failed, {len(skipped)} skipped."
    ]
    for item in outputs:
        name = ROLE_AGENT_NAMES[item["role"]]
        if item["status"] == "completed":
            lines.append(f"- {name}: {item['result']}")
        elif item["status"] == "failed":
            lines.append(f"- {name} (failed): {item.get('error') or item['result']}")
        else:
            lines.append(f"- {name} (skipped): {item['result']}")

    if completed and not failed:
        status: WorkerAggregateStatus = "completed"
    elif completed and failed:
        status = "partial"
    elif failed and not completed:
        status = "failed"
    else:
        status = "failed"

    return status, avg_confidence, "\n".join(lines)


async def run_worker_with_timeout(
    worker: WorkerCallable,
    worker_input: WorkerInput,
    timeout_seconds: int,
) -> WorkerOutput:
    """Execute one worker with timeout and error isolation."""
    try:
        raw = await asyncio.wait_for(worker(worker_input), timeout=timeout_seconds)
    except TimeoutError:
        return {
            "role": worker_input["role"],
            "status": "failed",
            "result": "",
            "error": f"Worker timed out after {timeout_seconds}s",
            "confidence": 0.0,
        }
    except Exception as exc:
        return {
            "role": worker_input["role"],
            "status": "failed",
            "result": "",
            "error": str(exc),
            "confidence": 0.0,
        }

    if not isinstance(raw, dict):
        return {
            "role": worker_input["role"],
            "status": "failed",
            "result": "",
            "error": "Worker returned an invalid payload.",
            "confidence": 0.0,
        }
    return raw  # type: ignore[return-value]


async def run_workers_parallel(
    roles: list[WorkerRole],
    state: AgentState,
    registry: WorkerRegistry,
    runtime_config: RuntimeConfig,
) -> list[WorkerOutput]:
    """Run selected workers in parallel with concurrency and timeout limits."""
    if not roles:
        return []

    task = extract_user_task(state)
    context = build_worker_context(state)
    timeout_seconds = runtime_config["worker_timeout_seconds"]
    max_concurrency = max(1, runtime_config["worker_max_concurrency"])
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_role(role: WorkerRole) -> WorkerOutput:
        worker = registry.get(role)
        if worker is None:
            return {
                "role": role,
                "status": "skipped",
                "result": f"No worker registered for role '{role}'.",
                "error": None,
                "confidence": 0.0,
            }

        worker_input: WorkerInput = {
            "role": role,
            "task": task,
            "context": context,
        }
        async with semaphore:
            return await run_worker_with_timeout(worker, worker_input, timeout_seconds)

    return list(await asyncio.gather(*(_run_role(role) for role in roles)))


def outputs_to_observations(outputs: list[WorkerOutput]) -> list[Observation]:
    """Convert worker outputs into graph observations."""
    observations: list[Observation] = []
    for item in outputs:
        observations.append(
            {
                "source": ROLE_AGENT_NAMES[item["role"]],
                "content": item["result"] or (item.get("error") or ""),
                "error": item.get("error"),
            }
        )
    return observations


@dataclass
class MultiAgentOrchestratorNode:
    """Select workers, execute them in parallel, and aggregate results."""

    registry_factory: Callable[[], WorkerRegistry] = default_worker_registry
    registry: WorkerRegistry | None = field(default=None, repr=False)

    def _registry(self) -> WorkerRegistry:
        if self.registry is not None:
            return self.registry
        return self.registry_factory()

    async def __call__(self, state: AgentState) -> AgentState:
        """Run selected workers in parallel and write aggregated state."""
        tracker = NodeTracker(state, "multi_agent_orchestrator")
        runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
        roles = select_worker_roles(state)
        outputs = await run_workers_parallel(
            roles,
            state,
            self._registry(),
            runtime_config,
        )
        aggregate_status, confidence, summary = aggregate_worker_outputs(outputs)

        orchestrator_result: AgentResult = {
            "agent_name": "orchestrator",
            "status": aggregate_status,
            "output": summary,
            "confidence": confidence,
        }
        worker_results = [worker_output_to_agent_result(item) for item in outputs]
        existing = list(state.get("agent_results", []))

        return tracker.finish(
            {
                "agent_results": [*existing, orchestrator_result, *worker_results],
                "observations": [
                    *state.get("observations", []),
                    *outputs_to_observations(outputs),
                ],
                "final_answer": state.get("final_answer") or summary,
            },
            summary=(
                f"workers={len(outputs)} aggregate={aggregate_status} "
                f"confidence={confidence:.2f}"
            ),
        )


def create_multi_agent_orchestrator_node(
    registry: WorkerRegistry | None = None,
    registry_factory: Callable[[], WorkerRegistry] | None = None,
) -> MultiAgentOrchestratorNode:
    """Create a multi-agent orchestrator node for graph wiring and tests."""
    if registry is not None:
        return MultiAgentOrchestratorNode(registry=registry)
    if registry_factory is not None:
        return MultiAgentOrchestratorNode(registry_factory=registry_factory)
    return MultiAgentOrchestratorNode()
