from langchain_core.messages import HumanMessage
from langgraph.pregel import Pregel

from agent.config import DEFAULT_OPENAI_MODEL_NAME, load_config
from agent.graph import graph
from agent.state import create_initial_state, message_content_text, message_role


def test_graph_compiles() -> None:
    assert isinstance(graph, Pregel)


def test_create_initial_state_uses_messages_contract() -> None:
    state = create_initial_state("hello")

    assert isinstance(state["messages"][0], HumanMessage)
    assert message_role(state["messages"][0]) == "user"
    assert message_content_text(state["messages"][0]) == "hello"
    assert "changeme" not in state


def test_load_config_uses_safe_defaults_and_redacts_secret_presence() -> None:
    config = load_config(
        {
            "OPENAI_API_KEY": "placeholder",
            "LANGSMITH_API_KEY": "",
            "REACT_MAX_STEPS": "5",
            "LLM_MAX_TOKENS": "2048",
        }
    )

    assert config.openai_api_key_present is True
    assert "placeholder" not in repr(config)
    assert config.langsmith_api_key_present is False
    assert config.openai_model_name == DEFAULT_OPENAI_MODEL_NAME
    assert config.react_max_steps == 5
    assert config.llm_max_tokens == 2048
    assert config.to_runtime_config()["react_max_steps"] == 5


def test_load_config_parses_mcp_servers_json() -> None:
    config = load_config(
        {
            "MCP_SERVERS": (
                "["
                '{"name":"filesystem","transport":"stdio","command":"npx",'
                '"args":["-y","@modelcontextprotocol/server-filesystem","./docs"]},'
                '{"name":"catalog","transport":"streamable_http",'
                '"url":"https://crowcrowcrow.com/api/mcp/mcp"}'
                "]"
            )
        }
    )

    assert len(config.mcp_servers) == 2
    assert config.mcp_servers[0]["name"] == "filesystem"
    assert config.mcp_servers[0]["args"] == [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "./docs",
    ]
    assert config.mcp_servers[1]["transport"] == "streamable_http"


def test_load_config_parses_guardrail_controls() -> None:
    config = load_config(
        {
            "GUARDRAIL_TOOL_ALLOWLIST": "filesystem.read_file,catalog.*",
            "GUARDRAIL_BLOCKED_TOPICS": "credential, malware",
            "MAX_TOOL_CALLS_PER_RUN": "3",
        }
    )

    assert config.guardrail_tool_allowlist == ("filesystem.read_file", "catalog.*")
    assert config.guardrail_blocked_topics == ("credential", "malware")
    assert config.max_tool_calls_per_run == 3
    runtime_config = config.to_runtime_config()
    assert runtime_config["guardrail_tool_allowlist"] == [
        "filesystem.read_file",
        "catalog.*",
    ]
    assert runtime_config["guardrail_blocked_topics"] == ["credential", "malware"]
    assert runtime_config["max_tool_calls_per_run"] == 3


def test_load_config_keeps_legacy_mcp_example_as_default_server() -> None:
    config = load_config(
        {
            "MCP_EXAMPLE_SERVER_COMMAND": "npx",
            "MCP_EXAMPLE_SERVER_ARGS": "-y server ./docs",
        }
    )

    assert config.mcp_servers == (
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "server", "./docs"],
        },
    )
