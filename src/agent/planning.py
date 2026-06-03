"""Plan schema helpers, validation, and execution state updates."""

from __future__ import annotations

from dataclasses import dataclass

from agent.state import Plan, PlanStep, PlanStepStatus


@dataclass(frozen=True)
class PlanValidationIssue:
    """Single plan validation failure."""

    code: str
    message: str


def validate_plan(plan: Plan, *, max_steps: int = 12) -> list[PlanValidationIssue]:
    """Reject plans with missing criteria, bad dependencies, or cycles."""
    issues: list[PlanValidationIssue] = []
    steps = plan.get("steps", [])

    if not steps:
        issues.append(
            PlanValidationIssue(
                code="empty_plan",
                message="Plan must contain at least one step.",
            )
        )
        return issues

    if len(steps) > max_steps:
        issues.append(
            PlanValidationIssue(
                code="too_many_steps",
                message=f"Plan exceeds max steps ({max_steps}).",
            )
        )

    step_ids = {step["id"] for step in steps}
    if len(step_ids) != len(steps):
        issues.append(
            PlanValidationIssue(
                code="duplicate_step_id",
                message="Plan step ids must be unique.",
            )
        )

    for step in steps:
        if not step.get("acceptance_criteria"):
            issues.append(
                PlanValidationIssue(
                    code="missing_acceptance_criteria",
                    message=f"Step '{step['id']}' is missing acceptance criteria.",
                )
            )
        for dependency in step.get("dependencies", []):
            if dependency not in step_ids:
                issues.append(
                    PlanValidationIssue(
                        code="unknown_dependency",
                        message=(
                            f"Step '{step['id']}' depends on unknown step "
                            f"'{dependency}'."
                        ),
                    )
                )

    cycle = _find_dependency_cycle(steps)
    if cycle:
        issues.append(
            PlanValidationIssue(
                code="dependency_cycle",
                message=f"Plan contains a dependency cycle: {' -> '.join(cycle)}.",
            )
        )

    return issues


def plan_validation_messages(issues: list[PlanValidationIssue]) -> list[str]:
    """Render validation issues for state and fallback output."""
    return [issue.message for issue in issues]


def find_next_runnable_step(plan: Plan) -> PlanStep | None:
    """Return the next pending step whose dependencies are completed."""
    completed = {
        step["id"]
        for step in plan.get("steps", [])
        if step["status"] == "completed"
    }
    for step in plan.get("steps", []):
        if step["status"] != "pending":
            continue
        if all(dep in completed for dep in step.get("dependencies", [])):
            return step
    return None


def update_step_status(
    plan: Plan,
    step_id: str,
    *,
    status: PlanStepStatus,
    result: str | None = None,
) -> Plan:
    """Return a plan copy with one step status/result updated."""
    updated_steps: list[PlanStep] = []
    for step in plan.get("steps", []):
        if step["id"] != step_id:
            updated_steps.append(step)
            continue
        updated: PlanStep = {
            **step,
            "status": status,
        }
        if result is not None:
            updated["result"] = result
        updated_steps.append(updated)
    return {**plan, "steps": updated_steps}


def refresh_plan_status(plan: Plan) -> Plan:
    """Derive aggregate plan status from step states."""
    steps = plan.get("steps", [])
    if not steps:
        return {**plan, "status": "failed"}

    statuses = {step["status"] for step in steps}
    if any(status == "failed" for status in statuses):
        return {**plan, "status": "failed"}

    if all(status in {"completed", "skipped"} for status in statuses):
        return {**plan, "status": "completed"}

    if any(status in {"running", "completed", "skipped"} for status in statuses):
        return {**plan, "status": "running"}

    return {**plan, "status": "pending"}


def summarize_plan_execution(plan: Plan) -> str:
    """Aggregate step outcomes into a final answer summary."""
    lines = ["Plan execution summary:"]
    completed = 0
    failed = 0
    skipped = 0
    pending = 0

    for step in plan.get("steps", []):
        status = step["status"]
        if status == "completed":
            completed += 1
        elif status == "failed":
            failed += 1
        elif status == "skipped":
            skipped += 1
        else:
            pending += 1

        result = step.get("result")
        detail = result if result else status
        lines.append(f"- [{status}] {step['title']}: {detail}")

    lines.append(
        f"Completed {completed}, failed {failed}, skipped {skipped}, pending {pending}."
    )
    if failed or pending:
        lines.append("Some steps did not finish successfully.")
    return "\n".join(lines)


def _find_dependency_cycle(steps: list[PlanStep]) -> list[str] | None:
    graph = {step["id"]: step.get("dependencies", []) for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            cycle_start = stack.index(node)
            return stack[cycle_start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in graph.get(node, []):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for step_id in graph:
        cycle = visit(step_id)
        if cycle:
            return cycle
    return None
