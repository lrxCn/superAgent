"""Unit tests for parallel multi-agent orchestration."""

from __future__ import annotations

import time

import pytest

from agent.nodes.orchestrator import (
    aggregate_worker_outputs,
    create_multi_agent_orchestrator_node,
    run_workers_parallel,
    select_worker_roles,
)
from agent.state import RuntimeConfig
from agent.workers.mock import MockWorkerBehavior, create_mock_worker_registry
from agent.workers.protocol import WorkerOutput

pytestmark = pytest.mark.anyio


def _runtime_config(
    *,
    max_concurrency: int = 4,
    timeout_seconds: int = 120,
) -> RuntimeConfig:
    return {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": max_concurrency,
        "worker_timeout_seconds": timeout_seconds,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": False,
        "reflection_enabled": True,
    }


def test_select_worker_roles_from_explicit_keywords() -> None:
    state = {
        "messages": [
            {
                "role": "user",
                "content": "Use researcher and reviewer agents in parallel.",
            }
        ],
        "intent_decision": {
            "path": "multi_agent_orchestrator",
            "reason": "test",
            "confidence": 0.9,
            "signals": ["multi_agent:parallel"],
            "requires_reflection": True,
        },
    }

    roles = select_worker_roles(state)

    assert roles == ["researcher", "reviewer"]


def test_select_worker_roles_defaults_when_unspecified() -> None:
    state = {
        "messages": [{"role": "user", "content": "Run agents in parallel."}],
        "intent_decision": {
            "path": "multi_agent_orchestrator",
            "reason": "test",
            "confidence": 0.9,
            "signals": ["multi_agent:parallel"],
            "requires_reflection": True,
        },
    }

    roles = select_worker_roles(state)

    assert roles == ["researcher", "coder", "reviewer"]


def test_aggregate_completed_when_all_workers_succeed() -> None:
    outputs: list[WorkerOutput] = [
        {
            "role": "researcher",
            "status": "completed",
            "result": "ok",
            "error": None,
            "confidence": 0.9,
        },
        {
            "role": "coder",
            "status": "completed",
            "result": "ok",
            "error": None,
            "confidence": 0.8,
        },
    ]

    status, confidence, _ = aggregate_worker_outputs(outputs)

    assert status == "completed"
    assert confidence == pytest.approx(0.85)


def test_aggregate_partial_when_some_workers_fail() -> None:
    outputs: list[WorkerOutput] = [
        {
            "role": "researcher",
            "status": "completed",
            "result": "ok",
            "error": None,
            "confidence": 0.9,
        },
        {
            "role": "coder",
            "status": "failed",
            "result": "",
            "error": "boom",
            "confidence": 0.0,
        },
    ]

    status, _, summary = aggregate_worker_outputs(outputs)

    assert status == "partial"
    assert "1 completed, 1 failed" in summary


async def test_run_workers_parallel_respects_concurrency() -> None:
    registry = create_mock_worker_registry(
        {
            "researcher": MockWorkerBehavior(delay_seconds=0.05),
            "coder": MockWorkerBehavior(delay_seconds=0.05),
            "reviewer": MockWorkerBehavior(delay_seconds=0.05),
        }
    )
    state = {
        "messages": [{"role": "user", "content": "parallel work"}],
    }
    config = _runtime_config(max_concurrency=1, timeout_seconds=5)

    started = time.monotonic()
    outputs = await run_workers_parallel(
        ["researcher", "coder", "reviewer"],
        state,
        registry,
        config,
    )
    elapsed = time.monotonic() - started

    assert len(outputs) == 3
    assert all(item["status"] == "completed" for item in outputs)
    assert elapsed >= 0.14


async def test_worker_timeout_marks_failed() -> None:
    registry = create_mock_worker_registry(
        {"researcher": MockWorkerBehavior(delay_seconds=0.2)}
    )
    state = {"messages": [{"role": "user", "content": "research task"}]}
    config = _runtime_config(timeout_seconds=0)

    outputs = await run_workers_parallel(
        ["researcher"],
        state,
        registry,
        config,
    )

    assert outputs[0]["status"] == "failed"
    assert "timed out" in (outputs[0].get("error") or "").lower()


async def test_worker_exception_marks_failed() -> None:
    registry = create_mock_worker_registry(
        {"coder": MockWorkerBehavior(raise_error="mock worker failure")}
    )
    state = {"messages": [{"role": "user", "content": "implement feature"}]}

    outputs = await run_workers_parallel(
        ["coder"],
        state,
        registry,
        _runtime_config(),
    )

    assert outputs[0]["status"] == "failed"
    assert "mock worker failure" in (outputs[0].get("error") or "")


async def test_orchestrator_node_returns_partial_on_mixed_results() -> None:
    registry = create_mock_worker_registry(
        {
            "researcher": MockWorkerBehavior(),
            "coder": MockWorkerBehavior(raise_error="coder failed"),
        }
    )
    node = create_multi_agent_orchestrator_node(registry=registry)
    state = {
        "messages": [
            {
                "role": "user",
                "content": "Use researcher and coder agents in parallel.",
            }
        ],
        "runtime_config": _runtime_config(),
        "agent_results": [],
        "observations": [],
        "intent_decision": {
            "path": "multi_agent_orchestrator",
            "reason": "test",
            "confidence": 0.9,
            "signals": [],
            "requires_reflection": True,
        },
    }

    result = await node(state)

    orchestrator = result["agent_results"][0]
    assert orchestrator["agent_name"] == "orchestrator"
    assert orchestrator["status"] == "partial"
    assert result["final_answer"]
    assert any(item["agent_name"] == "researcher_agent" for item in result["agent_results"])
    assert any(
        item["agent_name"] == "coder_agent" and item["status"] == "failed"
        for item in result["agent_results"]
    )


async def test_orchestrator_node_completes_all_default_workers() -> None:
    node = create_multi_agent_orchestrator_node(registry=create_mock_worker_registry())
    state = {
        "messages": [{"role": "user", "content": "Run agents in parallel."}],
        "runtime_config": _runtime_config(),
        "agent_results": [],
        "observations": [],
    }

    result = await node(state)

    orchestrator = result["agent_results"][0]
    assert orchestrator["status"] == "completed"
    worker_names = {item["agent_name"] for item in result["agent_results"][1:]}
    assert worker_names == {
        "researcher_agent",
        "coder_agent",
        "reviewer_agent",
    }


async def test_orchestrator_node_uses_production_registry_factory() -> None:
    node = create_multi_agent_orchestrator_node(
        registry_factory=lambda: create_mock_worker_registry(
            {"researcher": MockWorkerBehavior(confidence=0.91)}
        )
    )
    state = {
        "messages": [{"role": "user", "content": "Use researcher agent in parallel."}],
        "runtime_config": _runtime_config(),
        "agent_results": [],
        "observations": [],
    }

    result = await node(state)

    assert result["agent_results"][0]["status"] == "completed"
    assert result["agent_results"][1]["agent_name"] == "researcher_agent"
    assert result["agent_results"][1]["confidence"] == 0.91
