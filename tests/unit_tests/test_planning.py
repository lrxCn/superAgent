from agent.planning import (
    find_next_runnable_step,
    refresh_plan_status,
    update_step_status,
    validate_plan,
)
from agent.state import Plan, PlanStep


def _step(
    step_id: str,
    *,
    dependencies: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    status: str = "pending",
) -> PlanStep:
    return {
        "id": step_id,
        "title": step_id,
        "type": "llm",
        "dependencies": dependencies or [],
        "acceptance_criteria": acceptance_criteria or ["done"],
        "status": status,
    }


def test_validate_plan_rejects_missing_acceptance_criteria() -> None:
    plan: Plan = {
        "steps": [
            {
                "id": "a",
                "title": "Analyze",
                "type": "llm",
                "dependencies": [],
                "acceptance_criteria": [],
                "status": "pending",
            }
        ],
        "status": "pending",
    }

    issues = validate_plan(plan)

    assert any(issue.code == "missing_acceptance_criteria" for issue in issues)


def test_validate_plan_rejects_dependency_cycles() -> None:
    plan: Plan = {
        "steps": [
            _step("a", dependencies=["b"]),
            _step("b", dependencies=["a"]),
        ],
        "status": "pending",
    }

    issues = validate_plan(plan)

    assert any(issue.code == "dependency_cycle" for issue in issues)


def test_validate_plan_rejects_unknown_dependencies() -> None:
    plan: Plan = {
        "steps": [_step("a", dependencies=["missing"])],
        "status": "pending",
    }

    issues = validate_plan(plan)

    assert any(issue.code == "unknown_dependency" for issue in issues)


def test_find_next_runnable_step_respects_dependencies() -> None:
    plan: Plan = {
        "steps": [
            _step("first"),
            _step("second", dependencies=["first"]),
        ],
        "status": "pending",
    }

    assert find_next_runnable_step(plan)["id"] == "first"

    plan = update_step_status(plan, "first", status="completed", result="ok")
    assert find_next_runnable_step(plan)["id"] == "second"


def test_refresh_plan_status_marks_completed_plan() -> None:
    completed_step: PlanStep = {
        **_step("first"),
        "status": "completed",
        "result": "ok",
    }
    plan: Plan = {
        "steps": [completed_step],
        "status": "running",
    }

    refreshed = refresh_plan_status(plan)

    assert refreshed["status"] == "completed"
