from __future__ import annotations

import pytest

from agent.llm import FakeLLMClient
from agent.workers import default_worker_registry
from agent.workers.production import (
    LLMWorker,
    build_worker_messages,
    create_production_worker_registry,
)

pytestmark = pytest.mark.anyio


def _worker_input():
    return {
        "role": "researcher",
        "task": "Investigate worker behavior.",
        "context": "long_term=User prefers concise answers.",
    }


def test_build_worker_messages_uses_role_prompt_and_context() -> None:
    messages = build_worker_messages(_worker_input())

    assert messages[0]["role"] == "system"
    assert "researcher worker" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Investigate worker behavior." in messages[1]["content"]
    assert "User prefers concise answers." in messages[1]["content"]


async def test_llm_worker_returns_completed_output() -> None:
    worker = LLMWorker(
        role="researcher",
        llm_factory=lambda: FakeLLMClient(responses=["Researcher production output."]),
    )

    output = await worker(_worker_input())

    assert output == {
        "role": "researcher",
        "status": "completed",
        "result": "Researcher production output.",
        "error": None,
        "confidence": 0.82,
    }


async def test_llm_worker_marks_empty_output_failed() -> None:
    worker = LLMWorker(
        role="researcher",
        llm_factory=lambda: FakeLLMClient(responses=["   "]),
    )

    output = await worker(_worker_input())

    assert output["status"] == "failed"
    assert output["error"] == "Worker LLM returned an empty result."


async def test_production_registry_registers_all_roles_with_fake_llm() -> None:
    llm = FakeLLMClient(
        responses=[
            "research output",
            "code output",
            "review output",
            "memory output",
        ]
    )
    registry = create_production_worker_registry(llm_client=llm)

    outputs = []
    for role in ("researcher", "coder", "reviewer", "memory_manager"):
        worker = registry.get(role)
        assert worker is not None
        outputs.append(
            await worker(
                {
                    "role": role,
                    "task": "Run the worker.",
                    "context": "none",
                }
            )
        )

    assert [item["status"] for item in outputs] == ["completed"] * 4
    assert [item["result"] for item in outputs] == [
        "research output",
        "code output",
        "review output",
        "memory output",
    ]


def test_default_worker_registry_is_production_llm_backed() -> None:
    registry = default_worker_registry()
    worker = registry.get("researcher")

    assert isinstance(worker, LLMWorker)
