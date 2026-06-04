"""Runtime state schema for the SuperAgent graph."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict

MessageRole = Literal["system", "user", "assistant", "tool"]
Message = AnyMessage
RoutePath = Literal[
    "direct_answer",
    "react_agent",
    "planner",
    "multi_agent_orchestrator",
    "fallback",
]


class RuntimeConfig(TypedDict):
    """Per-run controls copied from environment defaults or caller input."""

    react_max_steps: int
    plan_max_steps: int
    worker_max_concurrency: int
    worker_timeout_seconds: int
    tool_timeout_seconds: int
    reflection_max_rounds: int
    memory_enabled: bool
    reflection_enabled: bool
    guardrail_tool_allowlist: NotRequired[list[str]]
    guardrail_blocked_topics: NotRequired[list[str]]
    max_tool_calls_per_run: NotRequired[int]


class MemoryContext(TypedDict):
    """Memory read results used by downstream runtime paths."""

    short_term: list[str]
    long_term: list[str]
    entities: list[str]
    errors: list[str]


class ContextBudget(TypedDict):
    """Estimated context usage and compression status."""

    limit: int
    estimated: int
    compressed: bool
    summary: str | None
    dropped_messages: int
    dropped_memories: int
    estimated_tokens: NotRequired[int]
    max_tokens: NotRequired[int]


class IntentDecision(TypedDict):
    """Router output consumed by path nodes."""

    path: RoutePath
    reason: str
    confidence: float
    signals: list[str]
    requires_reflection: bool


PlanStepType = Literal["llm", "tool", "agent"]
PlanStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
PlanStatus = Literal["not_started", "pending", "running", "completed", "failed"]


class PlanStep(TypedDict):
    """Planned work unit for plan-and-execute."""

    id: str
    title: str
    type: PlanStepType
    dependencies: list[str]
    acceptance_criteria: list[str]
    status: PlanStepStatus
    result: NotRequired[str | None]
    tool_name: NotRequired[str]
    tool_arguments: NotRequired[dict[str, object]]


class Plan(TypedDict):
    """Structured multi-step plan with validation and execution status."""

    steps: list[PlanStep]
    status: PlanStatus
    title: NotRequired[str]
    validation_errors: NotRequired[list[str]]


class MCPSession(TypedDict):
    """MCP server connection summary."""

    name: str
    status: Literal["not_configured", "connected", "failed"]
    tools: list[str]
    error: str | None


class ToolCall(TypedDict):
    """Tool invocation history entry."""

    tool_name: str
    arguments: dict[str, object]
    status: Literal["pending", "completed", "failed"]
    error: str | None


class Observation(TypedDict):
    """Observation produced by tools, planning steps, or worker agents."""

    source: str
    content: str
    error: str | None


class AgentResult(TypedDict):
    """Worker agent result placeholder."""

    agent_name: str
    status: Literal["completed", "partial", "failed", "skipped"]
    output: str
    confidence: float
    error: NotRequired[str | None]
    role: NotRequired[str]


class Evaluation(TypedDict):
    """Reflection/evaluator result placeholder."""

    enabled: bool
    status: Literal["not_required", "pass", "fail"]
    issues: list[str]
    suggestions: list[str]
    round: NotRequired[int]
    requires_revision: NotRequired[bool]
    gate_reasons: NotRequired[list[str]]
    skip_reason: NotRequired[str | None]
    source: NotRequired[Literal["rule", "llm"]]
    model: NotRequired[str | None]


class MemoryWriteResult(TypedDict):
    """Long-term memory write result."""

    status: Literal["not_attempted", "stored", "skipped", "error"]
    target: Literal["none", "graphiti", "checkpoint"]
    reason: str | None
    error: NotRequired[str | None]
    stored_count: NotRequired[int]


RuntimeEventStatus = Literal["started", "completed", "failed", "skipped"]
RuntimeEventName = Literal[
    "node",
    "route",
    "tool_call",
    "security",
    "fallback",
    "memory_write",
    "reflection",
]
ObservedPath = RoutePath | Literal["control", "unknown"]


class RuntimeEvent(TypedDict):
    """Structured runtime event for observability."""

    event: RuntimeEventName
    path: ObservedPath
    node: str
    status: RuntimeEventStatus
    duration_ms: int
    summary: str
    error_type: NotRequired[str | None]


class PathMetrics(TypedDict):
    """Aggregated metrics for the active execution path."""

    path: ObservedPath
    event_count: int
    nodes: list[str]
    total_duration_ms: int
    terminal_status: NotRequired[RuntimeEventStatus | None]


class AgentState(TypedDict, total=False):
    """Shared graph state.

    All fields are explicit so future nodes can add behavior without ad hoc
    dictionary keys drifting across task cards.
    """

    messages: Annotated[list[Message], add_messages]
    runtime_config: RuntimeConfig
    memory_context: MemoryContext
    context_budget: ContextBudget
    intent_decision: IntentDecision
    plan: Plan
    current_step: PlanStep | None
    mcp_sessions: list[MCPSession]
    tool_calls: list[ToolCall]
    observations: list[Observation]
    agent_results: list[AgentResult]
    evaluation: Evaluation
    reflection_round: NotRequired[int]
    reflection_exhausted: NotRequired[bool]
    fallback_reason: str | None
    memory_write_result: MemoryWriteResult
    final_answer: str
    step_observation_pending: NotRequired[Observation | None]
    step_result_pending: NotRequired[str | None]
    step_status_pending: NotRequired[PlanStepStatus | None]
    run_id: NotRequired[str]
    thread_id: NotRequired[str]
    runtime_events: NotRequired[list[RuntimeEvent]]
    path_metrics: NotRequired[PathMetrics]


def create_initial_state(message: str) -> AgentState:
    """Create the smallest valid caller input state."""
    return {"messages": [HumanMessage(content=message)]}


def message_role(message: Message) -> MessageRole:
    """Return an OpenAI-style role for a LangChain message."""
    if isinstance(message, BaseMessage):
        if message.type == "human":
            return "user"
        if message.type == "ai":
            return "assistant"
        if message.type in {"system", "tool"}:
            return cast(MessageRole, message.type)
        return "assistant"
    role = cast(dict[str, object], message).get("role")
    return cast(MessageRole, role if role in {"system", "user", "assistant", "tool"} else "user")


def message_content_text(message: Message) -> str:
    """Return message content as text for routing, memory, and prompts."""
    content: object
    if isinstance(message, BaseMessage):
        content = message.content
    else:
        content = cast(dict[str, object], message).get("content", "")

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def is_user_message(message: Message) -> bool:
    """Return whether a message came from the user/human role."""
    return message_role(message) == "user"
