import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.pregel import Pregel

from agent.config import load_config
from agent.graph import build_graph
from agent.memory import checkpoint


class DummyPostgresSaver:
    def __init__(self) -> None:
        self.setup_calls = 0

    async def setup(self) -> None:
        self.setup_calls += 1


class DummyPostgresContext:
    def __init__(self, saver: DummyPostgresSaver | None = None) -> None:
        self.saver = saver or DummyPostgresSaver()
        self.enter_calls = 0
        self.exit_calls = 0

    async def __aenter__(self) -> DummyPostgresSaver:
        self.enter_calls += 1
        return self.saver

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.exit_calls += 1


@pytest.mark.anyio
async def test_create_postgres_checkpointer_calls_setup_when_enabled(monkeypatch) -> None:
    context = DummyPostgresContext()
    monkeypatch.setattr(
        checkpoint.AsyncPostgresSaver,
        "from_conn_string",
        lambda conn_string: context,
    )

    resource = await checkpoint.create_postgres_checkpointer(
        load_config({"DATABASE_URL": "postgresql://example", "CHECKPOINT_SETUP": "true"})
    )

    assert resource.backend == "postgres"
    assert resource.checkpointer is context.saver
    assert resource.setup_called is True
    assert context.saver.setup_calls == 1
    await resource.aclose()
    assert context.exit_calls == 1


@pytest.mark.anyio
async def test_create_postgres_checkpointer_skips_setup_when_disabled(
    monkeypatch,
) -> None:
    context = DummyPostgresContext()
    monkeypatch.setattr(
        checkpoint.AsyncPostgresSaver,
        "from_conn_string",
        lambda conn_string: context,
    )

    resource = await checkpoint.create_postgres_checkpointer(
        load_config({"DATABASE_URL": "postgresql://example", "CHECKPOINT_SETUP": "false"})
    )

    assert resource.backend == "postgres"
    assert resource.setup_called is False
    assert context.saver.setup_calls == 0
    await resource.aclose()


@pytest.mark.anyio
async def test_create_postgres_checkpointer_falls_back_to_memory_on_error(
    monkeypatch,
) -> None:
    class FailingContext(DummyPostgresContext):
        async def __aenter__(self) -> DummyPostgresSaver:
            raise RuntimeError("database unavailable")

    context = FailingContext()
    monkeypatch.setattr(
        checkpoint.AsyncPostgresSaver,
        "from_conn_string",
        lambda conn_string: context,
    )

    resource = await checkpoint.create_postgres_checkpointer(
        load_config({"DATABASE_URL": "postgresql://example"})
    )

    assert resource.backend == "memory"
    assert isinstance(resource.checkpointer, InMemorySaver)
    assert resource.setup_called is False
    assert "database unavailable" in (resource.fallback_reason or "")
    assert context.exit_calls == 1


def test_build_graph_accepts_checkpointer() -> None:
    compiled = build_graph(checkpointer=InMemorySaver())

    assert isinstance(compiled, Pregel)
