"""ReAct tool loop runtime path."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from agent.config import AppConfig, load_config
from agent.llm import LLMClient, LLMProviderError, LLMRequest, create_siliconflow_llm
from agent.state import AgentState, MCPSession, Message, Observation, ToolCall
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

SYSTEM_PROMPT = (
    "You are SuperAgent's ReAct tool path. Choose one MCP tool per step or finish "
    "with a final answer. Respond with JSON only using one of these shapes:\n"
    '{"action":"call_tool","tool_name":"...","arguments":{...}}\n'
    '{"action":"finish","answer":"..."}\n'
    "Do not invent tools that are not listed."
)


@dataclass(frozen=True)
class ReActDecision:
    """Parsed model decision for one ReAct step."""

    action: str
    tool_name: str | None = None
    arguments: dict[str, object] = field(default_factory=dict)
    answer: str | None = None


@dataclass
class ReActNode:
    """Execute a bounded MCP-backed ReAct loop."""

    llm_factory: Callable[[], LLMClient] = create_siliconflow_llm
    mcp_factory: Callable[[], MCPClient] | None = None
    app_config: AppConfig | None = None

    async def __call__(self, state: AgentState) -> AgentState:
        """Connect to MCP, run the ReAct loop, and write tool history."""
        runtime_config = state.get("runtime_config") or load_config().to_runtime_config()
        max_steps = runtime_config["react_max_steps"]
        tool_timeout = float(runtime_config["tool_timeout_seconds"])
        tool_calls: list[ToolCall] = list(state.get("tool_calls", []))
        observations: list[Observation] = list(state.get("observations", []))

        client = self._create_client()
        if client is None:
            reason = "MCP tools are not configured for this run."
            return self._mcp_failure_state(
                state,
                session_name="example_filesystem",
                reason=reason,
                tool_calls=tool_calls,
                observations=observations,
            )

        try:
            await client.connect()
            tools = await client.list_tools()
        except MCPConnectionError as exc:
            await client.close()
            return self._mcp_failure_state(
                state,
                session_name=_session_name(client),
                reason=str(exc),
                tool_calls=tool_calls,
                observations=observations,
            )

        session: MCPSession = {
            "name": _session_name(client),
            "status": "connected",
            "tools": [tool.name for tool in tools],
            "error": None,
        }

        if not tools:
            await client.close()
            return self._mcp_failure_state(
                state,
                session_name=session["name"],
                reason="No MCP tools were discovered.",
                tool_calls=tool_calls,
                observations=observations,
                mcp_sessions=[session],
            )

        final_answer = state.get("final_answer")
        fallback_reason = state.get("fallback_reason")
        try:
            llm = self.llm_factory()
        except Exception as exc:
            await client.close()
            reason = f"ReAct LLM initialization failed: {exc}"
            return {
                "mcp_sessions": [session],
                "tool_calls": tool_calls,
                "observations": observations,
                "fallback_reason": reason,
                "final_answer": state.get("final_answer") or f"Fallback: {reason}",
            }

        for step in range(max_steps):
            try:
                llm_result = await llm.generate(
                    LLMRequest(
                        messages=build_react_messages(state, tools, observations),
                        temperature=0.0,
                    )
                )
            except LLMProviderError as exc:
                fallback_reason = str(exc)
                final_answer = state.get("final_answer") or f"Fallback: {exc}"
                break

            decision = parse_react_decision(llm_result.content)
            if decision is None:
                fallback_reason = "ReAct model returned invalid JSON."
                observations.append(
                    {
                        "source": "react_agent",
                        "content": "Invalid model JSON; stopping ReAct loop.",
                        "error": fallback_reason,
                    }
                )
                break

            if decision.action == "finish":
                final_answer = decision.answer or state.get("final_answer") or ""
                observations.append(
                    {
                        "source": "react_agent",
                        "content": f"ReAct finished after {step + 1} step(s).",
                        "error": None,
                    }
                )
                break

            if decision.action != "call_tool" or not decision.tool_name:
                fallback_reason = "ReAct model returned an unsupported action."
                break

            tool_spec = _find_tool(tools, decision.tool_name)
            if tool_spec is None:
                error = f"Unknown tool '{decision.tool_name}'."
                request = ToolCallRequest(
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                )
                tool_calls.append(
                    tool_call_to_state_entry(request, status="failed", error=error)
                )
                observations.append(observation_to_state_entry(
                    ToolObservation(
                        tool_name=decision.tool_name,
                        content=error,
                        success=False,
                        error=error,
                    )
                ))
                continue

            validation_error = validate_tool_arguments(tool_spec, decision.arguments)
            request = ToolCallRequest(
                tool_name=decision.tool_name,
                arguments=decision.arguments,
            )
            if validation_error:
                tool_calls.append(
                    tool_call_to_state_entry(
                        request,
                        status="failed",
                        error=validation_error,
                    )
                )
                observations.append(
                    observation_to_state_entry(
                        ToolObservation(
                            tool_name=decision.tool_name,
                            content=validation_error,
                            success=False,
                            error=validation_error,
                        )
                    )
                )
                continue

            try:
                observation = await client.call_tool(
                    decision.tool_name,
                    decision.arguments,
                    timeout_seconds=tool_timeout,
                )
            except MCPToolError as exc:
                error = str(exc)
                tool_calls.append(
                    tool_call_to_state_entry(request, status="failed", error=error)
                )
                observations.append(
                    observation_to_state_entry(
                        ToolObservation(
                            tool_name=decision.tool_name,
                            content=error,
                            success=False,
                            error=error,
                        )
                    )
                )
                continue

            tool_calls.append(
                tool_call_to_state_entry(
                    request,
                    status="completed" if observation.success else "failed",
                    error=observation.error,
                )
            )
            observations.append(observation_to_state_entry(observation))
        else:
            fallback_reason = f"ReAct loop exceeded max steps ({max_steps})."
            observations.append(
                {
                    "source": "react_agent",
                    "content": fallback_reason,
                    "error": fallback_reason,
                }
            )

        await client.close()

        if final_answer is None and fallback_reason:
            final_answer = state.get("final_answer") or f"Fallback: {fallback_reason}"

        return {
            "mcp_sessions": [session],
            "tool_calls": tool_calls,
            "observations": observations,
            "fallback_reason": fallback_reason,
            "final_answer": final_answer
            or state.get("final_answer")
            or "ReAct loop completed without a final answer.",
        }

    def _create_client(self) -> MCPClient | None:
        if self.mcp_factory is not None:
            return self.mcp_factory()
        config = self.app_config or load_config()
        if not config.mcp_example_server_command or not config.mcp_example_server_args:
            return None
        return create_mcp_client(build_example_mcp_config(config))

    def _mcp_failure_state(
        self,
        state: AgentState,
        *,
        session_name: str,
        reason: str,
        tool_calls: list[ToolCall],
        observations: list[Observation],
        mcp_sessions: list[MCPSession] | None = None,
    ) -> AgentState:
        session: MCPSession = {
            "name": session_name,
            "status": "failed",
            "tools": [],
            "error": reason,
        }
        return {
            "mcp_sessions": mcp_sessions or [session],
            "tool_calls": tool_calls,
            "observations": observations,
            "fallback_reason": reason,
            "final_answer": state.get("final_answer") or f"Fallback: {reason}",
        }


def create_react_node(
    llm_client: LLMClient | None = None,
    mcp_client: MCPClient | None = None,
) -> ReActNode:
    """Create a ReAct node with optional test doubles."""
    if llm_client is None:
        llm_factory: Callable[[], LLMClient] = create_siliconflow_llm
    else:
        llm_factory = lambda: llm_client
    mcp_factory = None if mcp_client is None else lambda: mcp_client
    return ReActNode(llm_factory=llm_factory, mcp_factory=mcp_factory)


def build_react_messages(
    state: AgentState,
    tools: list[ToolSpec],
    observations: list[Observation],
) -> list[Message]:
    """Build the prompt for one ReAct step."""
    user_goal = _latest_user_text(state)
    tool_lines = [
        f"- {tool.name}: {tool.description or 'no description'}"
        for tool in tools
    ]
    observation_lines = [
        f"[{item['source']}] {item['content']}"
        if not item.get("error")
        else f"[{item['source']}] error={item['error']}"
        for item in observations[-6:]
    ]
    user_content = "\n\n".join(
        [
            f"Current user goal:\n{user_goal}",
            "Available MCP tools:\n" + "\n".join(tool_lines),
            "Recent observations:\n"
            + ("\n".join(observation_lines) if observation_lines else "none"),
        ]
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_react_decision(raw: str) -> ReActDecision | None:
    """Parse one JSON ReAct decision from model output."""
    payload = _extract_json_object(raw)
    if payload is None:
        return None

    action = payload.get("action")
    if action == "finish":
        answer = payload.get("answer")
        return ReActDecision(
            action="finish",
            answer=str(answer) if answer is not None else "",
        )
    if action == "call_tool":
        tool_name = payload.get("tool_name")
        arguments = payload.get("arguments", {})
        if not isinstance(tool_name, str):
            return None
        if not isinstance(arguments, dict):
            return None
        return ReActDecision(
            action="call_tool",
            tool_name=tool_name,
            arguments=arguments,
        )
    return None


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


def _extract_json_object(raw: str) -> dict[str, object] | None:
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
