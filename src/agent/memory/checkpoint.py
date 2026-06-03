"""Checkpoint factory for short-term PostgreSQL memory."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent.config import AppConfig, load_config


class AsyncCheckpointSaver(Protocol):
    """Minimal checkpointer protocol used by graph compilation."""

    async def aget_tuple(self, *args: object, **kwargs: object) -> object:
        """Read a checkpoint tuple."""


@dataclass
class CheckpointerResource:
    """Checkpointer plus lifecycle metadata."""

    checkpointer: BaseCheckpointSaver[Any]
    backend: str
    setup_called: bool
    fallback_reason: str | None = None
    _context: AbstractAsyncContextManager[AsyncPostgresSaver] | None = None

    async def aclose(self) -> None:
        """Close the underlying PostgreSQL context when one exists."""
        if self._context is not None:
            await self._context.__aexit__(None, None, None)
            self._context = None


def create_memory_checkpointer(reason: str | None = None) -> CheckpointerResource:
    """Create an in-memory fallback checkpointer."""
    return CheckpointerResource(
        checkpointer=InMemorySaver(),
        backend="memory",
        setup_called=False,
        fallback_reason=reason,
    )


async def create_postgres_checkpointer(
    config: AppConfig | None = None,
) -> CheckpointerResource:
    """Create a PostgreSQL checkpointer, falling back to memory on failure."""
    config = load_config() if config is None else config
    if not config.database_url:
        return create_memory_checkpointer("DATABASE_URL is empty.")

    context = AsyncPostgresSaver.from_conn_string(config.database_url)
    try:
        checkpointer = await context.__aenter__()
        setup_called = False
        if config.checkpoint_setup:
            await checkpointer.setup()
            setup_called = True
    except Exception as exc:
        await context.__aexit__(None, None, None)
        return create_memory_checkpointer(
            f"PostgreSQL checkpointer unavailable: {exc}"
        )

    return CheckpointerResource(
        checkpointer=checkpointer,
        backend="postgres",
        setup_called=setup_called,
        _context=context,
    )
