from langgraph.pregel import Pregel

from agent.config import DEFAULT_OPENAI_MODEL_NAME, load_config
from agent.graph import graph
from agent.state import create_initial_state


def test_graph_compiles() -> None:
    assert isinstance(graph, Pregel)


def test_create_initial_state_uses_messages_contract() -> None:
    state = create_initial_state("hello")

    assert state == {"messages": [{"role": "user", "content": "hello"}]}
    assert "changeme" not in state


def test_load_config_uses_safe_defaults_and_redacts_secret_presence() -> None:
    config = load_config(
        {
            "OPENAI_API_KEY": "test-key",
            "LANGSMITH_API_KEY": "",
            "REACT_MAX_STEPS": "5",
            "LLM_MAX_TOKENS": "2048",
        }
    )

    assert config.openai_api_key_present is True
    assert config.langsmith_api_key_present is False
    assert config.openai_model_name == DEFAULT_OPENAI_MODEL_NAME
    assert config.react_max_steps == 5
    assert config.llm_max_tokens == 2048
    assert config.to_runtime_config()["react_max_steps"] == 5
