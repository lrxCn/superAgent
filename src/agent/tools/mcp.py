"""MCP client adapter, tool discovery, and call protocol."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

from agent.config import AppConfig, load_config
from agent.state import Observation, ToolCall

MAX_OBSERVATION_CHARS = 4000
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|token|secret|api[_-]?key|authorization|credential)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ToolSpec:
    """Discovered MCP tool metadata."""

    name: str
    description: str
    input_schema: dict[str, object]


@dataclass(frozen=True)
class ToolCallRequest:
    """Internal tool invocation request."""

    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolObservation:
    """Internal tool execution result before state mapping."""

    tool_name: str
    content: str
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class MCPStdioConfig:
    """Launch an MCP server as a child process."""

    command: str
    args: list[str]
    name: str = "example"
    cwd: str | None = None


@dataclass(frozen=True)
class MCPUrlConfig:
    """Connect to a remote MCP server over HTTP/SSE transport."""

    url: str
    transport: Literal["sse", "streamable_http"] = "sse"
    name: str = "remote"


MCPConfig = MCPStdioConfig | MCPUrlConfig


class MCPConnectionError(RuntimeError):
    """Raise when MCP server connection or discovery fails."""


class MCPToolError(RuntimeError):
    """Raise when a tool call fails before observation mapping."""


class MCPClient(Protocol):
    """Protocol consumed by the ReAct loop."""

    async def connect(self) -> None:
        """Connect to the MCP server and discover tools."""

    async def close(self) -> None:
        """Close the MCP session."""

    async def list_tools(self) -> list[ToolSpec]:
        """Return discovered tools."""

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> ToolObservation:
        """Execute a tool and return a sanitized observation."""


def build_example_mcp_config(config: AppConfig | None = None) -> MCPStdioConfig:
    """Build the filesystem MCP example config from environment defaults."""
    config = load_config() if config is None else config
    args = config.mcp_example_server_args.split()
    if not config.mcp_example_server_command or not args:
        raise MCPConnectionError("MCP example server command/args are not configured.")
    return MCPStdioConfig(
        command=config.mcp_example_server_command,
        args=args,
        name="example_filesystem",
    )


def validate_tool_arguments(
    spec: ToolSpec,
    arguments: dict[str, object],
) -> str | None:
    """Validate tool arguments against a minimal JSON schema subset."""
    schema = spec.input_schema
    schema_type = schema.get("type")
    if schema_type not in (None, "object"):
        return "Tool input schema must describe an object."

    required = schema.get("required", [])
    if not isinstance(required, list):
        return "Tool input schema has invalid required field."

    missing = [name for name in required if name not in arguments]
    if missing:
        return f"Missing required arguments: {', '.join(str(name) for name in missing)}"

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return "Tool input schema has invalid properties field."

    for key, value in arguments.items():
        if key not in properties:
            continue
        prop_schema = properties[key]
        if not isinstance(prop_schema, dict):
            continue
        expected_type = prop_schema.get("type")
        if expected_type and not _value_matches_type(value, expected_type):
            return f"Argument '{key}' must be of type {expected_type}."
    return None


def sanitize_tool_content(content: object) -> str:
    """Filter sensitive fields and truncate tool output."""
    sanitized = _sanitize_value(content)
    if isinstance(sanitized, str):
        rendered = sanitized
    else:
        rendered = json.dumps(sanitized, ensure_ascii=False, default=str)
    if len(rendered) <= MAX_OBSERVATION_CHARS:
        return rendered
    suffix = "... [truncated]"
    keep = max(0, MAX_OBSERVATION_CHARS - len(suffix))
    return rendered[:keep] + suffix


def observation_to_state_entry(
    observation: ToolObservation,
    *,
    source: str = "mcp_tool",
) -> Observation:
    """Map an internal tool observation to graph state."""
    return {
        "source": source,
        "content": observation.content,
        "error": observation.error,
    }


def tool_call_to_state_entry(
    request: ToolCallRequest,
    *,
    status: Literal["pending", "completed", "failed"],
    error: str | None = None,
) -> ToolCall:
    """Map an internal tool call to graph state."""
    return {
        "tool_name": request.tool_name,
        "arguments": request.arguments,
        "status": status,
        "error": error,
    }


@dataclass
class FakeMCPClient:
    """Deterministic MCP client for unit tests."""

    tools: list[ToolSpec] = field(default_factory=list)
    responses: dict[str, ToolObservation | Exception] = field(default_factory=dict)
    connect_error: Exception | None = None
    delay_seconds: float = 0.0
    connected: bool = False
    calls: list[ToolCallRequest] = field(default_factory=list)

    async def connect(self) -> None:
        """Simulate MCP connection."""
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    async def close(self) -> None:
        """Simulate MCP shutdown."""
        self.connected = False

    async def list_tools(self) -> list[ToolSpec]:
        """Return configured tools."""
        return list(self.tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> ToolObservation:
        """Return a configured response or raise."""
        self.calls.append(ToolCallRequest(tool_name=tool_name, arguments=arguments))
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        configured = self.responses.get(tool_name)
        if configured is None:
            return ToolObservation(
                tool_name=tool_name,
                content=sanitize_tool_content({"result": "ok"}),
                success=True,
            )
        if isinstance(configured, Exception):
            raise configured
        return configured


@dataclass
class StdioMCPClient:
    """Connect to an MCP server over stdio."""

    config: MCPStdioConfig
    _session: ClientSession | None = field(default=None, init=False, repr=False)
    _session_context: Any = field(default=None, init=False, repr=False)
    _stdio_context: Any = field(default=None, init=False, repr=False)
    _tools: list[ToolSpec] = field(default_factory=list, init=False, repr=False)

    async def connect(self) -> None:
        """Start the MCP server process and initialize a session."""
        parameters = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            cwd=self.config.cwd,
        )
        try:
            self._stdio_context = stdio_client(parameters)
            read, write = await self._stdio_context.__aenter__()
            self._session_context = ClientSession(read, write)
            self._session = await self._session_context.__aenter__()
            await self._session.initialize()
            tools_result = await self._session.list_tools()
        except Exception as exc:
            await self.close()
            raise MCPConnectionError(f"MCP stdio connection failed: {exc}") from exc

        self._tools = [
            ToolSpec(
                name=tool.name,
                description=tool.description or "",
                input_schema=_tool_input_schema(tool),
            )
            for tool in tools_result.tools
        ]

    async def close(self) -> None:
        """Close the MCP session and child process."""
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
            self._session = None
        if self._stdio_context is not None:
            await self._stdio_context.__aexit__(None, None, None)
            self._stdio_context = None
        self._tools = []

    async def list_tools(self) -> list[ToolSpec]:
        """Return tools discovered during connect."""
        return list(self._tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> ToolObservation:
        """Execute an MCP tool call with timeout handling."""
        if self._session is None:
            raise MCPConnectionError("MCP session is not connected.")

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise MCPToolError(f"Tool '{tool_name}' timed out after {timeout_seconds}s") from exc
        except Exception as exc:
            raise MCPToolError(f"Tool '{tool_name}' failed: {exc}") from exc

        if result.isError:
            content = _render_tool_result(result.content)
            return ToolObservation(
                tool_name=tool_name,
                content=sanitize_tool_content(content),
                success=False,
                error=content or f"Tool '{tool_name}' returned an error.",
            )

        content = sanitize_tool_content(_render_tool_result(result.content))
        return ToolObservation(
            tool_name=tool_name,
            content=content,
            success=True,
        )


@dataclass
class UrlMCPClient:
    """Placeholder for future URL/SSE MCP transport support."""

    config: MCPUrlConfig

    async def connect(self) -> None:
        """Raise until URL transport is implemented."""
        raise MCPConnectionError(
            f"MCP URL transport ({self.config.transport}) is not implemented yet."
        )

    async def close(self) -> None:
        """No-op placeholder."""

    async def list_tools(self) -> list[ToolSpec]:
        """Return no tools because URL transport is unavailable."""
        return []

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> ToolObservation:
        """Raise because URL transport is unavailable."""
        raise MCPConnectionError(
            f"MCP URL transport ({self.config.transport}) is not implemented yet."
        )


def create_mcp_client(config: MCPConfig) -> MCPClient:
    """Create an MCP client for stdio or URL transport configs."""
    if isinstance(config, MCPStdioConfig):
        return StdioMCPClient(config=config)
    return UrlMCPClient(config=config)


def _tool_input_schema(tool: object) -> dict[str, object]:
    schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def _render_tool_result(content: object) -> str:
    if not content:
        return ""
    parts: list[str] = []
    for item in cast(list[object], content):
        if isinstance(item, TextContent):
            parts.append(item.text)
        else:
            parts.append(str(item))
    return "\n".join(parts)


def _value_matches_type(value: object, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _sanitize_value(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_PATTERN.search(str(key)):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value
