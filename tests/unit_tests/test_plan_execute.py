import pytest

from agent.llm import FakeLLMClient
from agent.nodes.planner import (
    build_agent_step_input,
    create_execute_plan_node,
    create_plan_generate_node,
    create_plan_validate_node,
    create_step_observe_node,
    generate_deterministic_plan,
)
from agent.planning import validate_plan
from agent.state import Plan
from agent.tools.mcp import FakeMCPClient, ToolObservation, ToolSpec
from agent.workers.mock import create_mock_worker_registry
from agent.workers.registry import WorkerRegistry

pytestmark = pytest.mark.anyio


def _runtime_config() -> dict[str, object]:
    return {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }


async def test_plan_validate_rejects_invalid_plan() -> None:
    invalid_plan: Plan = {
        "steps": [
            {
                "id": "loop-a",
                "title": "A",
                "type": "llm",
                "dependencies": ["loop-b"],
                "acceptance_criteria": ["ok"],
                "status": "pending",
            },
            {
                "id": "loop-b",
                "title": "B",
                "type": "llm",
                "dependencies": ["loop-a"],
                "acceptance_criteria": ["ok"],
                "status": "pending",
            },
        ],
        "status": "pending",
    }
    node = create_plan_validate_node()

    result = await node(
        {
            "plan": invalid_plan,
            "runtime_config": _runtime_config(),
        }
    )

    assert result["plan"]["status"] == "failed"
    assert result["fallback_reason"]
    assert "cycle" in result["fallback_reason"].lower()


async def test_execute_plan_runs_llm_steps_and_records_observations() -> None:
    llm = FakeLLMClient(
        responses=[
            "analysis complete",
            "execution complete",
            "summary complete",
        ]
    )
    state = {
        "messages": [
            {"role": "user", "content": "Design and implement a migration plan."}
        ],
        "runtime_config": _runtime_config(),
        "plan": generate_deterministic_plan(
            {"messages": [{"role": "user", "content": "Design and implement a migration plan."}]}
        ),
        "observations": [],
        "tool_calls": [],
        "mcp_sessions": [],
    }
    state["plan"]["status"] = "running"
    execute = create_execute_plan_node(llm_client=llm)
    observe = create_step_observe_node()

    while state["plan"]["status"] == "running":
        executed = await execute(state)
        state = {**state, **executed}
        observed = await observe(state)
        state = {**state, **observed}
        if state["plan"]["status"] in {"completed", "failed"}:
            break

    assert state["plan"]["status"] == "completed"
    assert len(state["observations"]) == 3
    assert all(step["status"] == "completed" for step in state["plan"]["steps"])
    assert "Plan execution summary" in state["final_answer"]


async def test_execute_plan_runs_tool_step_with_mock_mcp() -> None:
    llm = FakeLLMClient(responses=["analysis", "execution", "summary"])
    mcp = FakeMCPClient(
        tools=[
            ToolSpec(
                name="read_file",
                description="Read a file",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            )
        ],
        responses={
            "read_file": ToolObservation(
                tool_name="read_file",
                content='{"text":"plan context"}',
                success=True,
            )
        },
    )
    generate = create_plan_generate_node()
    validate = create_plan_validate_node()
    execute = create_execute_plan_node(llm_client=llm, mcp_client=mcp)
    observe = create_step_observe_node()

    state = {
        "messages": [{"role": "user", "content": "Read project files and build a plan."}],
        "runtime_config": _runtime_config(),
        "observations": [],
        "tool_calls": [],
        "mcp_sessions": [],
    }
    state = {**state, **await generate(state)}
    state = {**state, **await validate(state)}

    while state["plan"]["status"] == "running":
        state = {**state, **await execute(state)}
        state = {**state, **await observe(state)}

    assert state["plan"]["status"] == "completed"
    assert any(step["type"] == "tool" for step in state["plan"]["steps"])
    assert state["tool_calls"]
    assert state["tool_calls"][0]["status"] == "completed"


async def test_agent_step_runs_worker_and_completes() -> None:
    plan: Plan = {
        "steps": [
            {
                "id": "delegate",
                "title": "Delegate to specialist agent",
                "type": "agent",
                "dependencies": [],
                "acceptance_criteria": ["Agent output recorded."],
                "status": "pending",
            }
        ],
        "status": "running",
    }
    execute = create_execute_plan_node(
        llm_client=FakeLLMClient(responses=["unused"]),
        worker_registry=create_mock_worker_registry(),
    )
    observe = create_step_observe_node()

    state = {
        "messages": [{"role": "user", "content": "plan"}],
        "runtime_config": _runtime_config(),
        "plan": plan,
        "observations": [],
    }
    state = {**state, **await execute(state)}
    state = {**state, **await observe(state)}

    assert state["plan"]["steps"][0]["status"] == "completed"
    assert "coder output" in state["plan"]["steps"][0]["result"].lower()
    assert state["observations"][0]["source"] == "plan_agent:delegate:coder_agent"


def test_agent_step_input_defaults_to_coder_role() -> None:
    step = {
        "id": "execute",
        "title": "Execute the planned work",
        "type": "agent",
        "dependencies": [],
        "acceptance_criteria": ["Primary work output is produced."],
        "status": "pending",
    }

    worker_input = build_agent_step_input(
        {"messages": [{"role": "user", "content": "Implement the task."}]},
        step,
    )

    assert worker_input["role"] == "coder"
    assert "Implement the task." in worker_input["task"]


async def test_agent_step_worker_error_marks_step_failed() -> None:
    async def failing_worker(_worker_input):
        raise RuntimeError("agent worker unavailable")

    registry = WorkerRegistry(workers={"coder": failing_worker})
    plan: Plan = {
        "steps": [
            {
                "id": "execute",
                "title": "Execute implementation",
                "type": "agent",
                "dependencies": [],
                "acceptance_criteria": ["Worker output recorded."],
                "status": "pending",
            }
        ],
        "status": "running",
    }
    execute = create_execute_plan_node(worker_registry=registry)
    observe = create_step_observe_node()
    state = {
        "messages": [{"role": "user", "content": "Implement a change."}],
        "runtime_config": _runtime_config(),
        "plan": plan,
        "observations": [],
        "tool_calls": [],
        "mcp_sessions": [],
    }

    state = {**state, **await execute(state)}
    state = {**state, **await observe(state)}

    assert state["plan"]["status"] == "failed"
    assert state["plan"]["steps"][0]["status"] == "failed"
    assert "agent worker unavailable" in state["plan"]["steps"][0]["result"]


def test_generated_plan_passes_validation() -> None:
    plan = generate_deterministic_plan(
        {"messages": [{"role": "user", "content": "Implement feature X step by step."}]}
    )

    assert not validate_plan(plan, max_steps=12)
