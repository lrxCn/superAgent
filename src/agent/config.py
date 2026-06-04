"""Runtime configuration defaults for SuperAgent."""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field
from typing import Mapping

from dotenv import dotenv_values

from agent.state import RuntimeConfig

DEFAULT_OPENAI_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_OPENAI_MODEL_NAME = "Pro/moonshotai/Kimi-K2.6"
DEFAULT_LANGCHAIN_PROJECT = "SUPER_AGENT"
DEFAULT_LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list(env: Mapping[str, str], name: str) -> list[str]:
    value = env.get(name)
    if value is None or value == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class AppConfig:
    """Environment-derived configuration with secrets redacted from repr."""

    langchain_tracing_v2: bool
    langchain_project: str
    langchain_endpoint: str
    langsmith_api_key_present: bool
    openai_api_key_present: bool
    openai_base_url: str
    openai_model_name: str
    llm_timeout_seconds: int
    llm_max_tokens: int
    react_max_steps: int
    plan_max_steps: int
    worker_max_concurrency: int
    worker_timeout_seconds: int
    tool_timeout_seconds: int
    reflection_max_rounds: int
    database_url: str
    checkpoint_setup: bool
    mcp_example_server_command: str
    mcp_example_server_args: str
    mcp_servers: tuple[dict[str, object], ...]
    mcp_tool_timeout_seconds: int
    guardrail_tool_allowlist: tuple[str, ...]
    guardrail_blocked_topics: tuple[str, ...]
    max_tool_calls_per_run: int
    graphiti_backend: str
    graphiti_mcp_url: str
    falkordb_url: str
    openai_api_key: str | None = field(default=None, repr=False)

    def to_runtime_config(self) -> RuntimeConfig:
        """Return per-run controls stored in graph state."""
        return {
            "react_max_steps": self.react_max_steps,
            "plan_max_steps": self.plan_max_steps,
            "worker_max_concurrency": self.worker_max_concurrency,
            "worker_timeout_seconds": self.worker_timeout_seconds,
            "tool_timeout_seconds": self.tool_timeout_seconds,
            "reflection_max_rounds": self.reflection_max_rounds,
            "memory_enabled": True,
            "reflection_enabled": True,
            "guardrail_tool_allowlist": list(self.guardrail_tool_allowlist),
            "guardrail_blocked_topics": list(self.guardrail_blocked_topics),
            "max_tool_calls_per_run": self.max_tool_calls_per_run,
        }


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Load runtime defaults from environment variables."""
    env = _load_environment() if env is None else env
    return AppConfig(
        langchain_tracing_v2=_env_bool(env, "LANGCHAIN_TRACING_V2", True),
        langchain_project=env.get("LANGCHAIN_PROJECT", DEFAULT_LANGCHAIN_PROJECT),
        langchain_endpoint=env.get("LANGCHAIN_ENDPOINT", DEFAULT_LANGCHAIN_ENDPOINT),
        langsmith_api_key_present=bool(env.get("LANGSMITH_API_KEY")),
        openai_api_key=env.get("OPENAI_API_KEY") or None,
        openai_api_key_present=bool(env.get("OPENAI_API_KEY")),
        openai_base_url=env.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
        openai_model_name=env.get("OPENAI_MODEL_NAME", DEFAULT_OPENAI_MODEL_NAME),
        llm_timeout_seconds=_env_int(env, "LLM_TIMEOUT_SECONDS", 60),
        llm_max_tokens=_env_int(env, "LLM_MAX_TOKENS", 4096),
        react_max_steps=_env_int(env, "REACT_MAX_STEPS", 8),
        plan_max_steps=_env_int(env, "PLAN_MAX_STEPS", 12),
        worker_max_concurrency=_env_int(env, "WORKER_MAX_CONCURRENCY", 4),
        worker_timeout_seconds=_env_int(env, "WORKER_TIMEOUT_SECONDS", 120),
        tool_timeout_seconds=_env_int(env, "TOOL_TIMEOUT_SECONDS", 30),
        reflection_max_rounds=_env_int(env, "REFLECTION_MAX_ROUNDS", 1),
        database_url=env.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable",
        ),
        checkpoint_setup=_env_bool(env, "CHECKPOINT_SETUP", True),
        mcp_example_server_command=env.get("MCP_EXAMPLE_SERVER_COMMAND", "npx"),
        mcp_example_server_args=env.get(
            "MCP_EXAMPLE_SERVER_ARGS",
            "-y @modelcontextprotocol/server-filesystem ./docs",
        ),
        mcp_servers=_env_mcp_servers(env),
        mcp_tool_timeout_seconds=_env_int(env, "MCP_TOOL_TIMEOUT_SECONDS", 30),
        guardrail_tool_allowlist=tuple(_env_list(env, "GUARDRAIL_TOOL_ALLOWLIST")),
        guardrail_blocked_topics=tuple(_env_list(env, "GUARDRAIL_BLOCKED_TOPICS")),
        max_tool_calls_per_run=_env_int(env, "MAX_TOOL_CALLS_PER_RUN", 0),
        graphiti_backend=env.get("GRAPHITI_BACKEND", "falkordb"),
        graphiti_mcp_url=env.get("GRAPHITI_MCP_URL", "http://localhost:8000"),
        falkordb_url=env.get("FALKORDB_URL", "redis://localhost:6379"),
    )


def _load_environment() -> Mapping[str, str]:
    file_env = {
        key: value
        for key, value in dotenv_values(".env").items()
        if value is not None
    }
    return {**file_env, **os.environ}


def _env_mcp_servers(env: Mapping[str, str]) -> tuple[dict[str, object], ...]:
    raw = env.get("MCP_SERVERS")
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, list):
            return ()
        return tuple(
            normalized
            for item in payload
            if isinstance(item, dict)
            for normalized in [_normalize_mcp_server(item)]
            if normalized is not None
        )

    command = env.get("MCP_EXAMPLE_SERVER_COMMAND", "npx")
    args = shlex.split(
        env.get(
            "MCP_EXAMPLE_SERVER_ARGS",
            "-y @modelcontextprotocol/server-filesystem ./docs",
        )
    )
    if not command or not args:
        return ()
    return (
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": command,
            "args": args,
        },
    )


def _normalize_mcp_server(item: Mapping[str, object]) -> dict[str, object] | None:
    name = str(item.get("name") or "").strip()
    transport = str(item.get("transport") or "stdio").strip().lower().replace("-", "_")
    if not name or transport not in {"stdio", "sse", "streamable_http"}:
        return None

    if transport == "stdio":
        command = str(item.get("command") or "").strip()
        raw_args = item.get("args", [])
        if isinstance(raw_args, str):
            args = shlex.split(raw_args)
        elif isinstance(raw_args, list):
            args = [str(arg) for arg in raw_args]
        else:
            args = []
        if not command:
            return None
        normalized: dict[str, object] = {
            "name": name,
            "transport": transport,
            "command": command,
            "args": args,
        }
        if item.get("cwd"):
            normalized["cwd"] = str(item["cwd"])
        return normalized

    url = str(item.get("url") or "").strip()
    if not url:
        return None
    normalized = {
        "name": name,
        "transport": transport,
        "url": url,
    }
    headers = item.get("headers")
    if isinstance(headers, dict):
        normalized["headers"] = {
            str(key): str(value)
            for key, value in headers.items()
        }
    timeout = item.get("timeout_seconds")
    if isinstance(timeout, int | float):
        normalized["timeout_seconds"] = float(timeout)
    read_timeout = item.get("sse_read_timeout_seconds")
    if isinstance(read_timeout, int | float):
        normalized["sse_read_timeout_seconds"] = float(read_timeout)
    if item.get("terminate_on_close") is not None:
        normalized["terminate_on_close"] = _coerce_bool(item["terminate_on_close"])
    return normalized


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
