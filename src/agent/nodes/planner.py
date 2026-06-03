"""Plan-and-execute runtime nodes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from agent.config import AppConfig, load_config
from agent.llm import LLMClient, LLMProviderError, LLMRequest, create_siliconflow_llm
from agent.observability import NodeTracker, safe_summary
from agent.planning import (
    find_next_runnable_step,
    plan_validation_messages,
    refresh_plan_status,
    summarize_plan_execution,
    update_step_status,
    validate_plan,
)
from agent.state import (
    AgentState,
    MCPSession,
    Message,
    Observation,
    Plan,
    PlanStep,
    ToolCall,
)
from agent.tools.mcp import (
    MCPClient,
    MCPConnectionError,
    MCPToolError,
    ToolCallRequest,
    ToolObservation,
    ToolSpec,
    build_example_mcp_config,
    create_mcp_client,
    observation_to_state_entry,
    tool_call_to_state_entry,
    validate_tool_arguments,
)

TOOL_KEYWORDS = (
    "file",
    "read",
    "write",
    "tool",
    "mcp",
    "search",
    "fetch",
    "文件",
    "读取",
    "工具",
)

LLM_STEP_PROMPT = (
    "You are executing one plan step for SuperAgent. Produce concise step output "
    "that satisfies the acceptance criteria. Do not claim to have used tools "
    "unless this step explicitly requires them."
)


@dataclass
class PlanGenerateNode:
    """Create a deterministic structured plan from the user goal."""

    max_steps: int | None = None

    async def __call__(self, state: AgentState) -> AgentState:
        """Generate a structured plan from the current user goal."""
        tracker = NodeTracker(state, "plan_generate")
        runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
        limit = self.max_steps or runtime_config["plan_max_steps"]
        plan = generate_deterministic_plan(state, max_steps=limit)
        return tracker.finish(
            {"plan": plan, "current_step": None},
            summary=f"plan_steps={len(plan['steps'])} status={plan['status']}",
        )


@dataclass
class PlanValidateNode:
    """Validate plan structure before execution."""

    async def __call__(self, state: AgentState) -> AgentState:
        """Validate the current plan or route to fallback on failure."""
        tracker = NodeTracker(state, "plan_validate")
        runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
        plan = state.get("plan") or {"steps": [], "status": "pending"}
        issues = validate_plan(plan, max_steps=runtime_config["plan_max_steps"])
        if issues:
            messages = plan_validation_messages(issues)
            reason = "Plan validation failed: " + "; ".join(messages)
            return tracker.finish(
                {
                    "plan": {
                        **plan,
                        "status": "failed",
                        "validation_errors": messages,
                    },
                    "fallback_reason": reason,
                    "final_answer": state.get("final_answer") or f"Fallback: {reason}",
                },
                summary=safe_summary(reason, max_chars=160),
                status="failed",
                error_type="PlanValidationError",
            )

        validated: Plan = {**plan, "status": "running", "validation_errors": []}
        return tracker.finish(
            {"plan": validated},
            summary=f"plan_validated steps={len(validated['steps'])}",
        )


@dataclass
class ExecutePlanNode:
    """Execute one runnable plan step."""

    llm_factory: Callable[[], LLMClient] = create_siliconflow_llm
    mcp_factory: Callable[[], MCPClient] | None = None
    app_config: AppConfig | None = None
    _tools: list[ToolSpec] = field(default_factory=list, repr=False)
    _mcp_session: MCPSession | None = field(default=None, repr=False)

    async def __call__(self, state: AgentState) -> AgentState:
        """Run the next runnable plan step and stage its observation."""
        tracker = NodeTracker(state, "execute_plan")
        plan = state.get("plan") or {"steps": [], "status": "failed"}
        if plan.get("status") == "failed":
            return tracker.finish({}, summary="plan_already_failed", status="skipped")

        step = find_next_runnable_step(plan)
        if step is None:
            refreshed = refresh_plan_status(plan)
            final_answer = state.get("final_answer") or summarize_plan_execution(refreshed)
            return tracker.finish(
                {
                    "plan": refreshed,
                    "current_step": None,
                    "final_answer": final_answer,
                },
                summary=f"plan_status={refreshed['status']}",
            )

        running_plan = update_step_status(plan, step["id"], status="running")
        tool_calls = list(state.get("tool_calls", []))
        mcp_sessions = list(state.get("mcp_sessions", []))

        try:
            if step["type"] == "llm":
                result, observation, fallback_reason = await self._execute_llm_step(
                    state, step
                )
            elif step["type"] == "tool":
                result, observation, fallback_reason, tool_calls, mcp_sessions = (
                    await self._execute_tool_step(state, step, tool_calls, mcp_sessions)
                )
            else:
                result = "Agent step deferred until multi-agent orchestration is available."
                observation = {
                    "source": f"plan_step:{step['id']}",
                    "content": result,
                    "error": None,
                }
                fallback_reason = None
                running_plan = update_step_status(
                    running_plan,
                    step["id"],
                    status="skipped",
                    result=result,
                )
        except LLMProviderError as exc:
            result = str(exc)
            observation = {
                "source": f"plan_step:{step['id']}",
                "content": result,
                "error": result,
            }
            fallback_reason = result
            running_plan = update_step_status(
                running_plan,
                step["id"],
                status="failed",
                result=result,
            )

        current_step = next(
            item for item in running_plan["steps"] if item["id"] == step["id"]
        )
        updates: AgentState = {
            "plan": running_plan,
            "current_step": current_step,
            "tool_calls": tool_calls,
            "mcp_sessions": mcp_sessions,
            "step_observation_pending": observation,
        }
        if fallback_reason:
            updates["fallback_reason"] = fallback_reason
        if step["type"] != "agent":
            updates["step_result_pending"] = result
            updates["step_status_pending"] = (
                "failed" if observation.get("error") else "completed"
            )
        return tracker.finish(
            updates,
            summary=f"step={step['id']} type={step['type']}",
            status="failed" if observation.get("error") else "completed",
            error_type="PlanStepError" if observation.get("error") else None,
        )

    async def _execute_llm_step(
        self,
        state: AgentState,
        step: PlanStep,
    ) -> tuple[str, Observation, str | None]:
        llm = self.llm_factory()
        messages = build_llm_step_messages(state, step)
        result = await llm.generate(LLMRequest(messages=messages, temperature=0.2))
        content = result.content.strip()
        observation: Observation = {
            "source": f"plan_step:{step['id']}",
            "content": content,
            "error": None,
        }
        return content, observation, None

    async def _execute_tool_step(
        self,
        state: AgentState,
        step: PlanStep,
        tool_calls: list[ToolCall],
        mcp_sessions: list[MCPSession],
    ) -> tuple[str, Observation, str | None, list[ToolCall], list[MCPSession]]:
        client = self._create_client()
        if client is None:
            reason = "MCP tools are not configured for plan tool steps."
            observation: Observation = {
                "source": f"plan_step:{step['id']}",
                "content": reason,
                "error": reason,
            }
            return reason, observation, reason, tool_calls, mcp_sessions

        try:
            if not self._tools:
                await client.connect()
                self._tools = await client.list_tools()
                self._mcp_session = {
                    "name": _session_name(client),
                    "status": "connected",
                    "tools": [tool.name for tool in self._tools],
                    "error": None,
                }
                mcp_sessions = [*mcp_sessions, self._mcp_session]
        except MCPConnectionError as exc:
            reason = str(exc)
            session: MCPSession = {
                "name": _session_name(client),
                "status": "failed",
                "tools": [],
                "error": reason,
            }
            observation = {
                "source": f"plan_step:{step['id']}",
                "content": reason,
                "error": reason,
            }
            await client.close()
            return reason, observation, reason, tool_calls, [*mcp_sessions, session]

        tool_name = step.get("tool_name") or (self._tools[0].name if self._tools else "")
        tool_spec = _find_tool(self._tools, tool_name)
        arguments = step.get("tool_arguments") or _default_tool_arguments(step)
        request = ToolCallRequest(tool_name=tool_name, arguments=arguments)
        runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
        tool_timeout = float(runtime_config["tool_timeout_seconds"])

        if tool_spec is None:
            error = f"Unknown tool '{tool_name}'."
            tool_calls.append(tool_call_to_state_entry(request, status="failed", error=error))
            observation = observation_to_state_entry(
                ToolObservation(tool_name=tool_name, content=error, success=False, error=error)
            )
            await client.close()
            return error, observation, error, tool_calls, mcp_sessions

        validation_error = validate_tool_arguments(tool_spec, arguments)
        if validation_error:
            tool_calls.append(
                tool_call_to_state_entry(request, status="failed", error=validation_error)
            )
            observation = observation_to_state_entry(
                ToolObservation(
                    tool_name=tool_name,
                    content=validation_error,
                    success=False,
                    error=validation_error,
                )
            )
            await client.close()
            return validation_error, observation, validation_error, tool_calls, mcp_sessions

        try:
            tool_observation = await client.call_tool(
                tool_name,
                arguments,
                timeout_seconds=tool_timeout,
            )
        except MCPToolError as exc:
            error = str(exc)
            tool_calls.append(tool_call_to_state_entry(request, status="failed", error=error))
            observation = observation_to_state_entry(
                ToolObservation(
                    tool_name=tool_name,
                    content=error,
                    success=False,
                    error=error,
                )
            )
            await client.close()
            return error, observation, error, tool_calls, mcp_sessions

        tool_calls.append(
            tool_call_to_state_entry(
                request,
                status="completed" if tool_observation.success else "failed",
                error=tool_observation.error,
            )
        )
        observation = observation_to_state_entry(tool_observation)
        await client.close()
        self._tools = []
        self._mcp_session = None
        content = tool_observation.content
        fallback = tool_observation.error
        return content, observation, fallback, tool_calls, mcp_sessions

    def _create_client(self) -> MCPClient | None:
        if self.mcp_factory is not None:
            return self.mcp_factory()
        config = self.app_config or load_config()
        if not config.mcp_example_server_command or not config.mcp_example_server_args:
            return None
        return create_mcp_client(build_example_mcp_config(config))


@dataclass
class StepObserveNode:
    """Persist step observations and advance plan state."""

    async def __call__(self, state: AgentState) -> AgentState:
        """Record the latest step observation and refresh aggregate plan status."""
        tracker = NodeTracker(state, "step_observe")
        plan = state.get("plan") or {"steps": [], "status": "failed"}
        current_step = state.get("current_step")
        observation = state.get("step_observation_pending")
        observations = list(state.get("observations", []))

        if observation:
            observations.append(observation)

        if current_step and current_step["type"] != "agent":
            status = state.get("step_status_pending") or current_step["status"]
            result = state.get("step_result_pending")
            if status in {"completed", "failed"}:
                plan = update_step_status(
                    plan,
                    current_step["id"],
                    status=status,
                    result=result,
                )

        plan = refresh_plan_status(plan)
        final_answer = state.get("final_answer")
        if plan["status"] in {"completed", "failed"} and not final_answer:
            final_answer = summarize_plan_execution(plan)

        updates: AgentState = {
            "plan": plan,
            "observations": observations,
            "current_step": current_step,
        }
        if final_answer is not None:
            updates["final_answer"] = final_answer
        return tracker.finish(
            updates,
            summary=f"plan_status={plan['status']} observations={len(observations)}",
        )


def create_plan_generate_node(max_steps: int | None = None) -> PlanGenerateNode:
    """Create the deterministic plan generation node."""
    return PlanGenerateNode(max_steps=max_steps)


def create_plan_validate_node() -> PlanValidateNode:
    """Create the plan validation node."""
    return PlanValidateNode()


def create_execute_plan_node(
    llm_client: LLMClient | None = None,
    mcp_client: MCPClient | None = None,
) -> ExecutePlanNode:
    """Create the plan execution node with optional test doubles."""
    llm_factory: Callable[[], LLMClient]
    if llm_client is None:
        llm_factory = create_siliconflow_llm
    else:
        injected_llm = llm_client

        def llm_factory() -> LLMClient:
            return injected_llm

    mcp_factory: Callable[[], MCPClient] | None = None
    if mcp_client is not None:
        injected_mcp = mcp_client

        def mcp_factory() -> MCPClient:
            return injected_mcp

    return ExecutePlanNode(llm_factory=llm_factory, mcp_factory=mcp_factory)


def create_step_observe_node() -> StepObserveNode:
    """Create the step observation node."""
    return StepObserveNode()


def generate_deterministic_plan(state: AgentState, *, max_steps: int = 12) -> Plan:
    """Build a stable multi-step plan from the latest user goal."""
    goal = _latest_user_text(state)
    use_tool_step = _contains_tool_signal(goal)
    steps: list[PlanStep] = [
        {
            "id": "analyze",
            "title": "Analyze the user goal",
            "type": "llm",
            "dependencies": [],
            "acceptance_criteria": ["Goal requirements and constraints are captured."],
            "status": "pending",
        }
    ]

    if use_tool_step:
        steps.append(
            {
                "id": "gather",
                "title": "Gather external or file-backed context",
                "type": "tool",
                "dependencies": ["analyze"],
                "acceptance_criteria": ["Required tool output is captured."],
                "status": "pending",
                "tool_name": "read_file",
                "tool_arguments": {"path": "README.md"},
            }
        )
        execute_dependencies = ["gather"]
    else:
        execute_dependencies = ["analyze"]

    steps.append(
        {
            "id": "execute",
            "title": "Execute the planned work",
            "type": "llm",
            "dependencies": execute_dependencies,
            "acceptance_criteria": ["Primary work output is produced."],
            "status": "pending",
        }
    )
    steps.append(
        {
            "id": "summarize",
            "title": "Summarize outcomes and remaining risks",
            "type": "llm",
            "dependencies": ["execute"],
            "acceptance_criteria": ["Completion status and risks are documented."],
            "status": "pending",
        }
    )

    if len(steps) > max_steps:
        steps = steps[:max_steps]

    title = goal.strip().splitlines()[0][:120] if goal.strip() else "Generated plan"
    return {
        "title": title,
        "steps": steps,
        "status": "pending",
    }


def build_llm_step_messages(state: AgentState, step: PlanStep) -> list[Message]:
    """Build the prompt for one LLM plan step."""
    goal = _latest_user_text(state)
    criteria = "; ".join(step.get("acceptance_criteria", []))
    prior_results = _prior_step_results(state.get("plan"))
    user_content = "\n\n".join(
        [
            f"Overall user goal:\n{goal}",
            f"Current step:\n{step['title']} ({step['id']})",
            f"Acceptance criteria:\n{criteria}",
            "Prior step results:\n" + (prior_results or "none"),
        ]
    )
    return [
        {"role": "system", "content": LLM_STEP_PROMPT},
        {"role": "user", "content": user_content},
    ]


def choose_plan_validate_path(state: AgentState) -> str:
    """Route invalid plans to fallback."""
    plan = state.get("plan") or {"steps": [], "status": "failed"}
    if plan.get("status") == "failed" or state.get("fallback_reason"):
        return "fallback"
    return "execute_plan"


def choose_plan_execution_path(state: AgentState) -> str:
    """Continue executing or finish the planner path."""
    plan = state.get("plan") or {"steps": [], "status": "failed"}
    if plan.get("status") in {"completed", "failed"}:
        return "memory_write"
    if find_next_runnable_step(plan) is not None:
        return "execute_plan"
    refreshed = refresh_plan_status(plan)
    if refreshed["status"] in {"completed", "failed"}:
        return "memory_write"
    return "execute_plan"


def _prior_step_results(plan: Plan | None) -> str:
    if not plan:
        return ""
    lines = []
    for step in plan.get("steps", []):
        if step.get("result"):
            lines.append(f"- {step['id']}: {step['result']}")
    return "\n".join(lines)


def _contains_tool_signal(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return any(keyword in normalized for keyword in TOOL_KEYWORDS)


def _default_tool_arguments(step: PlanStep) -> dict[str, object]:
    if step.get("tool_arguments"):
        return step["tool_arguments"]
    return {"path": "README.md"}


def _find_tool(tools: list[ToolSpec], tool_name: str) -> ToolSpec | None:
    for tool in tools:
        if tool.name == tool_name:
            return tool
    return None


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if message["role"] == "user":
            return message["content"]
    return ""


def _session_name(client: MCPClient) -> str:
    config = getattr(client, "config", None)
    if config is not None and hasattr(config, "name"):
        return str(config.name)
    return "mcp"


def parse_plan_step_payload(raw: str) -> dict[str, object] | None:
    """Parse JSON plan payloads in tests or future LLM planners."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
