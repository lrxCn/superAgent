"""MCP client adapter, tool discovery, and call protocol."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
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
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    sse_read_timeout_seconds: float = 300.0
    terminate_on_close: bool = False


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


def build_mcp_configs(config: AppConfig | None = None) -> list[MCPConfig]:
    """Build all configured MCP server definitions."""
    config = load_config() if config is None else config
    if not config.mcp_servers:
        return []

    configs: list[MCPConfig] = []
    for item in config.mcp_servers:
        transport = str(item.get("transport") or "stdio").replace("-", "_")
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if transport == "stdio":
            raw_args = item.get("args", [])
            args = [str(arg) for arg in raw_args] if isinstance(raw_args, list) else []
            configs.append(
                MCPStdioConfig(
                    command=str(item.get("command") or ""),
                    args=args,
                    name=name,
                    cwd=str(item["cwd"]) if item.get("cwd") else None,
                )
            )
            continue
        if transport in {"sse", "streamable_http"}:
            configs.append(
                MCPUrlConfig(
                    url=str(item.get("url") or ""),
                    transport=cast(Literal["sse", "streamable_http"], transport),
                    name=name,
                    headers=(
                        cast(dict[str, str], item.get("headers"))
                        if isinstance(item.get("headers"), dict)
                        else {}
                    ),
                    timeout_seconds=_config_float(
                        item.get("timeout_seconds"),
                        30.0,
                    ),
                    sse_read_timeout_seconds=_config_float(
                        item.get("sse_read_timeout_seconds"),
                        300.0,
                    ),
                    terminate_on_close=bool(item.get("terminate_on_close", False)),
                )
            )
    return configs


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
    config: object | None = None

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
    """Connect to an MCP server over SSE or Streamable HTTP."""

    config: MCPUrlConfig
    _session: ClientSession | None = field(default=None, init=False, repr=False)
    _session_context: Any = field(default=None, init=False, repr=False)
    _transport_context: Any = field(default=None, init=False, repr=False)
    _http_client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _tools: list[ToolSpec] = field(default_factory=list, init=False, repr=False)
    _session_id: str | None = field(default=None, init=False, repr=False)

    async def connect(self) -> None:
        """Initialize an MCP session over URL transport."""
        try:
            if self.config.transport == "sse":
                self._transport_context = sse_client(
                    self.config.url,
                    headers=self.config.headers or None,
                    timeout=self.config.timeout_seconds,
                    sse_read_timeout=self.config.sse_read_timeout_seconds,
                )
                read, write = await self._transport_context.__aenter__()
            else:
                timeout = httpx.Timeout(
                    self.config.timeout_seconds,
                    read=self.config.sse_read_timeout_seconds,
                )
                self._http_client = httpx.AsyncClient(
                    headers=self.config.headers or None,
                    timeout=timeout,
                )
                self._transport_context = streamable_http_client(
                    self.config.url,
                    http_client=self._http_client,
                    terminate_on_close=self.config.terminate_on_close,
                )
                read, write, get_session_id = await self._transport_context.__aenter__()
                self._session_id = get_session_id()

            self._session_context = ClientSession(read, write)
            self._session = await self._session_context.__aenter__()
            await self._session.initialize()
            tools_result = await self._session.list_tools()
        except Exception as exc:
            await self.close()
            raise MCPConnectionError(
                f"MCP URL connection failed for '{self.config.name}': {exc}"
            ) from exc

        self._tools = [
            ToolSpec(
                name=tool.name,
                description=tool.description or "",
                input_schema=_tool_input_schema(tool),
            )
            for tool in tools_result.tools
        ]

    async def close(self) -> None:
        """Close the MCP session and URL transport."""
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
            self._session = None
        if self._transport_context is not None:
            await self._transport_context.__aexit__(None, None, None)
            self._transport_context = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
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

        return ToolObservation(
            tool_name=tool_name,
            content=sanitize_tool_content(_render_tool_result(result.content)),
            success=True,
        )


@dataclass
class MultiMCPClient:
    """Aggregate multiple MCP servers and route calls by qualified tool name."""

    configs: list[MCPConfig]
    clients: list[MCPClient] = field(default_factory=list)
    _tools: list[ToolSpec] = field(default_factory=list, init=False, repr=False)
    _tool_routes: dict[str, tuple[MCPClient, str]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _server_tools: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False)
    _errors: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _close_errors: list[str] = field(default_factory=list, init=False, repr=False)

    async def connect(self) -> None:
        """Connect to all configured servers and expose namespaced tools."""
        if not self.clients:
            self.clients = [create_mcp_client(config) for config in self.configs]
        self._tools = []
        self._tool_routes = {}
        self._server_tools = {}
        self._errors = {}

        for client in self.clients:
            server_name = server_name_for_client(client)
            try:
                await client.connect()
                tools = await client.list_tools()
            except MCPConnectionError as exc:
                self._errors[server_name] = str(exc)
                continue

            self._server_tools[server_name] = []
            for tool in tools:
                qualified = qualify_tool_name(server_name, tool.name)
                self._tool_routes[qualified] = (client, tool.name)
                self._server_tools[server_name].append(qualified)
                self._tools.append(
                    ToolSpec(
                        name=qualified,
                        description=_qualified_description(server_name, tool.description),
                        input_schema=tool.input_schema,
                    )
                )

        self._add_unqualified_aliases()
        if not self._tools:
            message = "No MCP tools were discovered."
            if self._errors:
                details = "; ".join(
                    f"{server}: {error}" for server, error in self._errors.items()
                )
                message = f"{message} {details}"
            raise MCPConnectionError(message)

    async def close(self) -> None:
        """Close all child MCP clients."""
        errors: list[str] = []
        for client in self.clients:
            try:
                await client.close()
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as exc:
                errors.append(str(exc))
        self._tools = []
        self._tool_routes = {}
        self._close_errors = errors

    async def list_tools(self) -> list[ToolSpec]:
        """Return all discovered qualified tools."""
        return list(self._tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> ToolObservation:
        """Route a tool call to the configured server."""
        route = self._tool_routes.get(tool_name)
        if route is None:
            route = self._resolve_unqualified(tool_name)
        if route is None:
            raise MCPToolError(f"Unknown MCP tool '{tool_name}'.")

        client, raw_tool_name = route
        observation = await client.call_tool(
            raw_tool_name,
            arguments,
            timeout_seconds=timeout_seconds,
        )
        server_name = server_name_for_client(client)
        return ToolObservation(
            tool_name=qualify_tool_name(server_name, observation.tool_name),
            content=observation.content,
            success=observation.success,
            error=observation.error,
        )

    def session_summaries(self) -> list[dict[str, object]]:
        """Return connection summaries for graph state."""
        summaries: list[dict[str, object]] = []
        server_names = [
            server_name_for_config(config)
            for config in self.configs
        ] or [server_name_for_client(client) for client in self.clients]
        for server_name in server_names:
            error = self._errors.get(server_name)
            summaries.append(
                {
                    "name": server_name,
                    "status": "failed" if error else "connected",
                    "tools": self._server_tools.get(server_name, []),
                    "error": error,
                }
            )
        return summaries

    def _add_unqualified_aliases(self) -> None:
        raw_to_routes: dict[str, list[tuple[MCPClient, str]]] = {}
        raw_to_spec: dict[str, ToolSpec] = {}
        for qualified, route in self._tool_routes.items():
            raw_name = route[1]
            raw_to_routes.setdefault(raw_name, []).append(route)
            raw_to_spec[raw_name] = next(
                tool for tool in self._tools if tool.name == qualified
            )

        for raw_name, routes in raw_to_routes.items():
            if len(routes) != 1 or raw_name in self._tool_routes:
                continue
            self._tool_routes[raw_name] = routes[0]
            raw_spec = raw_to_spec[raw_name]
            self._tools.append(
                ToolSpec(
                    name=raw_name,
                    description=raw_spec.description,
                    input_schema=raw_spec.input_schema,
                )
            )

    def _resolve_unqualified(self, tool_name: str) -> tuple[MCPClient, str] | None:
        matches = [
            route
            for qualified, route in self._tool_routes.items()
            if qualified.endswith(f".{tool_name}")
        ]
        if len(matches) == 1:
            return matches[0]
        return None


def create_mcp_client(config: MCPConfig) -> MCPClient:
    """Create an MCP client for stdio or URL transport configs."""
    if isinstance(config, MCPStdioConfig):
        return StdioMCPClient(config=config)
    return UrlMCPClient(config=config)


def create_multi_mcp_client(configs: list[MCPConfig]) -> MCPClient:
    """Create a single client that routes across multiple MCP servers."""
    return MultiMCPClient(configs=configs)


def create_configured_mcp_client(config: AppConfig | None = None) -> MCPClient | None:
    """Create the configured MCP client, preserving no-server as None."""
    configs = build_mcp_configs(config)
    if not configs:
        return None
    return create_multi_mcp_client(configs)


def qualify_tool_name(server_name: str, tool_name: str) -> str:
    """Return the server-qualified tool name used for routing."""
    if tool_name.startswith(f"{server_name}."):
        return tool_name
    return f"{server_name}.{tool_name}"


def split_tool_name(tool_name: str) -> tuple[str | None, str]:
    """Split an optional ``server.tool`` name into server and raw tool parts."""
    server, separator, raw_name = tool_name.partition(".")
    if not separator:
        return None, tool_name
    return server, raw_name


def server_name_for_client(client: MCPClient) -> str:
    """Read the configured server name from a client."""
    config = getattr(client, "config", None)
    if config is not None and hasattr(config, "name"):
        return str(config.name)
    return "mcp"


def server_name_for_config(config: MCPConfig) -> str:
    """Read the configured server name from config."""
    return str(config.name)


def _tool_input_schema(tool: object) -> dict[str, object]:
    schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def _config_float(value: object, default: float) -> float:
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


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


def _qualified_description(server_name: str, description: str) -> str:
    prefix = f"[{server_name}]"
    if description:
        return f"{prefix} {description}"
    return prefix
