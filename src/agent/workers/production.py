"""Production LLM-backed workers for multi-agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from langchain_core.messages import MessageLikeRepresentation

from agent.llm import LLMClient, LLMRequest, create_siliconflow_llm
from agent.observability import safe_summary
from agent.workers.protocol import WorkerCallable, WorkerInput, WorkerOutput, WorkerRole
from agent.workers.registry import WorkerRegistry

ROLE_SYSTEM_PROMPTS: dict[WorkerRole, str] = {
    "researcher": (
        "You are SuperAgent's researcher worker. Find the relevant facts, "
        "constraints, unknowns, and evidence needed to answer or execute the task. "
        "Do not invent external facts; call out missing evidence explicitly."
    ),
    "coder": (
        "You are SuperAgent's coder worker. Produce implementation-oriented output: "
        "concrete changes, interfaces, tests, and risks. Keep the result actionable "
        "and grounded in the provided context."
    ),
    "reviewer": (
        "You are SuperAgent's reviewer worker. Look for correctness, regressions, "
        "missing tests, safety risks, and unclear assumptions. Prioritize findings "
        "over general commentary."
    ),
    "memory_manager": (
        "You are SuperAgent's memory manager worker. Extract only durable user "
        "preferences, project facts, decisions, and reusable context. Avoid secrets, "
        "transient status, and unsupported guesses."
    ),
}

WORKER_USER_TEMPLATE = """Task:
{task}

Relevant context:
{context}

Return concise role-specific output. If the task cannot be completed from the
available context, explain the blocker and the next useful step."""


@dataclass(frozen=True)
class LLMWorker:
    """One role-specific worker backed by the configured LLM provider."""

    role: WorkerRole
    llm_factory: Callable[[], LLMClient]
    confidence: float = 0.82

    async def __call__(self, worker_input: WorkerInput) -> WorkerOutput:
        """Run the role prompt and normalize provider failures."""
        try:
            llm = self.llm_factory()
            response = await llm.generate(
                LLMRequest(
                    messages=build_worker_messages(worker_input),
                    temperature=0.2,
                )
            )
        except Exception as exc:
            return {
                "role": self.role,
                "status": "failed",
                "result": "",
                "error": safe_summary(exc, max_chars=200),
                "confidence": 0.0,
            }

        result = response.content.strip()
        if not result:
            return {
                "role": self.role,
                "status": "failed",
                "result": "",
                "error": "Worker LLM returned an empty result.",
                "confidence": 0.0,
            }

        return {
            "role": self.role,
            "status": "completed",
            "result": result,
            "error": None,
            "confidence": self.confidence,
        }


def build_worker_messages(worker_input: WorkerInput) -> list[MessageLikeRepresentation]:
    """Build the role-specific prompt passed to the worker LLM."""
    role = worker_input["role"]
    return [
        {"role": "system", "content": ROLE_SYSTEM_PROMPTS[role]},
        {
            "role": "user",
            "content": WORKER_USER_TEMPLATE.format(
                task=worker_input["task"] or "No task provided.",
                context=worker_input["context"] or "none",
            ),
        },
    ]


def create_production_worker_registry(
    *,
    llm_client: LLMClient | None = None,
    llm_factory: Callable[[], LLMClient] | None = None,
) -> WorkerRegistry:
    """Create LLM-backed workers for all supported roles."""
    if llm_client is not None:
        injected_llm = llm_client

        def resolved_factory() -> LLMClient:
            return injected_llm

    else:
        resolved_factory = llm_factory or create_siliconflow_llm

    workers: dict[WorkerRole, WorkerCallable] = {
        role: LLMWorker(role=role, llm_factory=resolved_factory)
        for role in ROLE_SYSTEM_PROMPTS
    }
    return WorkerRegistry(workers=workers)
