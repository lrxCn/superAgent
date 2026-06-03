import pytest
from pydantic import SecretStr

from agent.config import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL_NAME,
    load_config,
)
from agent.llm import (
    FakeLLMClient,
    LLMConfigurationError,
    LLMRequest,
    create_siliconflow_llm,
)


@pytest.mark.anyio
async def test_fake_llm_returns_deterministic_response_and_records_calls() -> None:
    client = FakeLLMClient(responses=["first", "second"])
    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])

    first = await client.generate(request)
    second = await client.generate(request)

    assert first.content == "first"
    assert second.content == "second"
    assert first.provider == "fake"
    assert client.calls == [request, request]


def test_create_siliconflow_llm_requires_api_key() -> None:
    config = load_config({})

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        create_siliconflow_llm(config)


def test_create_siliconflow_llm_passes_openai_compatible_parameters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("agent.llm.ChatOpenAI", DummyChatOpenAI)
    config = load_config(
        {
            "OPENAI_API_KEY": "placeholder",
            "OPENAI_BASE_URL": DEFAULT_OPENAI_BASE_URL,
            "OPENAI_MODEL_NAME": DEFAULT_OPENAI_MODEL_NAME,
            "LLM_TIMEOUT_SECONDS": "11",
            "LLM_MAX_TOKENS": "222",
        }
    )

    client = create_siliconflow_llm(config)

    assert client.config.openai_model_name == DEFAULT_OPENAI_MODEL_NAME
    assert isinstance(captured["api_key"], SecretStr)
    assert captured["api_key"].get_secret_value() == "placeholder"
    assert captured == {
        "model": DEFAULT_OPENAI_MODEL_NAME,
        "api_key": captured["api_key"],
        "base_url": DEFAULT_OPENAI_BASE_URL,
        "timeout": 11,
        "max_completion_tokens": 222,
    }
