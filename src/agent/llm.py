"""SiliconFlow OpenAI-compatible LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from langchain_core.messages import (
    BaseMessage,
    MessageLikeRepresentation,
    convert_to_messages,
)
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent.config import AppConfig, load_config


@dataclass(frozen=True)
class LLMRequest:
    """Provider-independent chat completion request."""

    messages: list[MessageLikeRepresentation]
    temperature: float | None = None


@dataclass(frozen=True)
class LLMResult:
    """Provider-independent chat completion result."""

    content: str
    model: str
    provider: str = "siliconflow"


class LLMClient(Protocol):
    """Protocol consumed by runtime nodes that need model output."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        """Generate a chat completion."""


class LLMConfigurationError(RuntimeError):
    """Raise when required LLM configuration is missing."""


class LLMProviderError(RuntimeError):
    """Raise when the provider call fails."""


@dataclass
class SiliconFlowLLMClient:
    """Call SiliconFlow through the OpenAI-compatible ChatOpenAI client."""

    config: AppConfig
    chat_model: ChatOpenAI

    async def generate(self, request: LLMRequest) -> LLMResult:
        """Generate a chat completion through SiliconFlow."""
        try:
            response = await self.chat_model.ainvoke(
                _to_langchain_messages(request.messages),
                config={"metadata": {"provider": "siliconflow"}},
            )
        except Exception as exc:
            raise LLMProviderError(f"SiliconFlow LLM call failed: {exc}") from exc
        return LLMResult(
            content=str(response.content),
            model=self.config.openai_model_name,
        )


def _to_langchain_messages(
    messages: list[MessageLikeRepresentation],
) -> list[BaseMessage]:
    """Normalize dicts, tuples, and BaseMessage instances for chat models."""
    return convert_to_messages(messages)


@dataclass
class FakeLLMClient:
    """Return deterministic responses for tests."""

    responses: list[str] = field(default_factory=lambda: ["fake response"])
    model: str = "fake-model"
    calls: list[LLMRequest] = field(default_factory=list)

    async def generate(self, request: LLMRequest) -> LLMResult:
        """Generate a fake chat completion."""
        self.calls.append(request)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return LLMResult(
            content=self.responses[index],
            model=self.model,
            provider="fake",
        )


def create_siliconflow_llm(config: AppConfig | None = None) -> SiliconFlowLLMClient:
    """Create the only real first-phase LLM provider client."""
    config = load_config() if config is None else config
    if not config.openai_api_key:
        raise LLMConfigurationError(
            "OPENAI_API_KEY is required for SiliconFlow LLM calls."
        )

    chat_model = ChatOpenAI(
        model=config.openai_model_name,
        api_key=SecretStr(config.openai_api_key),
        base_url=config.openai_base_url,
        timeout=config.llm_timeout_seconds,
        max_completion_tokens=config.llm_max_tokens,
    )
    return SiliconFlowLLMClient(config=config, chat_model=chat_model)
