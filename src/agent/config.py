"""Runtime configuration defaults for SuperAgent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

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
    mcp_tool_timeout_seconds: int
    graphiti_backend: str
    graphiti_mcp_url: str
    falkordb_url: str

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
        }


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Load runtime defaults from environment variables."""
    env = os.environ if env is None else env
    return AppConfig(
        langchain_tracing_v2=_env_bool(env, "LANGCHAIN_TRACING_V2", True),
        langchain_project=env.get("LANGCHAIN_PROJECT", DEFAULT_LANGCHAIN_PROJECT),
        langchain_endpoint=env.get("LANGCHAIN_ENDPOINT", DEFAULT_LANGCHAIN_ENDPOINT),
        langsmith_api_key_present=bool(env.get("LANGSMITH_API_KEY")),
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
        mcp_tool_timeout_seconds=_env_int(env, "MCP_TOOL_TIMEOUT_SECONDS", 30),
        graphiti_backend=env.get("GRAPHITI_BACKEND", "falkordb"),
        graphiti_mcp_url=env.get("GRAPHITI_MCP_URL", "http://localhost:8000"),
        falkordb_url=env.get("FALKORDB_URL", "redis://localhost:6379"),
    )
