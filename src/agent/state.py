"""Runtime state schema for the SuperAgent graph."""

from __future__ import annotations

from typing import Literal

from typing_extensions import NotRequired, TypedDict

MessageRole = Literal["system", "user", "assistant", "tool"]
RoutePath = Literal[
    "direct_answer",
    "react_agent",
    "planner",
    "multi_agent_orchestrator",
    "fallback",
]


class Message(TypedDict):
    """Conversation message carried through graph state."""

    role: MessageRole
    content: str


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


class MemoryContext(TypedDict):
    """Memory read results used by downstream runtime paths."""

    short_term: list[str]
    long_term: list[str]
    entities: list[str]
    errors: list[str]


class ContextBudget(TypedDict):
    """Estimated context usage and compression status."""

    estimated_tokens: int
    max_tokens: int
    compressed: bool
    summary: str | None


class IntentDecision(TypedDict):
    """Router output consumed by path nodes."""

    path: RoutePath
    reason: str
    confidence: float


class PlanStep(TypedDict):
    """Planned work unit for later plan-and-execute tasks."""

    id: str
    description: str
    dependencies: list[str]
    acceptance_criteria: list[str]
    status: Literal["pending", "running", "completed", "failed", "skipped"]


class Plan(TypedDict):
    """Plan-and-execute state placeholder."""

    steps: list[PlanStep]
    status: Literal["not_started", "pending", "running", "completed", "failed"]


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


class Evaluation(TypedDict):
    """Reflection/evaluator result placeholder."""

    enabled: bool
    status: Literal["not_required", "pass", "fail"]
    issues: list[str]
    suggestions: list[str]


class MemoryWriteResult(TypedDict):
    """Long-term memory write result."""

    status: Literal["not_attempted", "stored", "skipped", "error"]
    reason: str | None


class AgentState(TypedDict, total=False):
    """Shared graph state.

    All fields are explicit so future nodes can add behavior without ad hoc
    dictionary keys drifting across task cards.
    """

    messages: list[Message]
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
    fallback_reason: str | None
    memory_write_result: MemoryWriteResult
    final_answer: str
    run_id: NotRequired[str]
    thread_id: NotRequired[str]


def create_initial_state(message: str) -> AgentState:
    """Create the smallest valid caller input state."""
    return {"messages": [{"role": "user", "content": message}]}
