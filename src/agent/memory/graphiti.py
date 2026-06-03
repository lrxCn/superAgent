"""Graphiti long-term memory client boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import httpx

from agent.config import AppConfig, load_config


@dataclass(frozen=True)
class MemoryRecord:
    """Long-term memory record returned by a client."""

    content: str
    source: str = "graphiti"
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MemorySearchResult:
    """Search result with fallback metadata."""

    records: list[MemoryRecord]
    backend: str
    error: str | None = None


@dataclass(frozen=True)
class MemoryWrite:
    """Write request for long-term memory."""

    content: str
    source: str
    metadata: dict[str, object] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class MemoryWriteResult:
    """Write result with fallback metadata."""

    status: str
    backend: str
    error: str | None = None


class LongTermMemoryClient(Protocol):
    """Protocol consumed by runtime memory nodes."""

    async def health(self) -> bool:
        """Return whether the long-term memory backend is reachable."""

    async def search(self, query: str, *, limit: int = 5) -> MemorySearchResult:
        """Search long-term memory."""

    async def write(self, memory: MemoryWrite) -> MemoryWriteResult:
        """Write long-term memory."""


class GraphitiMemoryError(RuntimeError):
    """Raise when a Graphiti call fails unexpectedly."""


def _mcp_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/mcp/"


def _health_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/health"


@dataclass
class GraphitiMemoryClient:
    """Access local Graphiti MCP server over HTTP."""

    base_url: str
    backend: str = "falkordb"
    timeout_seconds: float = 5.0
    http_client: httpx.AsyncClient | None = None

    async def health(self) -> bool:
        """Return whether the Graphiti service is reachable."""
        try:
            async with self._client() as client:
                response = await client.get(_health_url(self.base_url))
                if response.status_code < 500:
                    return True
        except httpx.HTTPError:
            pass
        try:
            payload: dict[str, object] = {
                "jsonrpc": "2.0",
                "id": "superagent-memory-status",
                "method": "tools/call",
                "params": {"name": "get_status", "arguments": {}},
            }
            await self._post_mcp(payload)
            return True
        except Exception:
            return False

    async def search(self, query: str, *, limit: int = 5) -> MemorySearchResult:
        """Search Graphiti via MCP tools/call, falling back to an empty result."""
        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": "superagent-memory-search",
            "method": "tools/call",
            "params": {
                "name": "search_nodes",
                "arguments": {"query": query, "limit": limit},
            },
        }
        try:
            response = await self._post_mcp(payload)
            records = self._parse_records(response.json())
            return MemorySearchResult(records=records, backend=self.backend)
        except Exception as exc:
            return MemorySearchResult(records=[], backend=self.backend, error=str(exc))

    async def write(self, memory: MemoryWrite) -> MemoryWriteResult:
        """Write Graphiti episode via MCP tools/call, falling back to skipped."""
        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": "superagent-memory-write",
            "method": "tools/call",
            "params": {
                "name": "add_episode",
                "arguments": {
                    "name": memory.source,
                    "episode_body": memory.content,
                    "source": "text",
                    "source_description": "SuperAgent long-term memory",
                    "reference_time": memory.timestamp,
                    "metadata": memory.metadata,
                },
            },
        }
        try:
            await self._post_mcp(payload)
            return MemoryWriteResult(status="stored", backend=self.backend)
        except Exception as exc:
            return MemoryWriteResult(status="skipped", backend=self.backend, error=str(exc))

    def _client(self):
        if self.http_client is not None:
            return _BorrowedAsyncClient(self.http_client)
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    async def _post_mcp(self, payload: dict[str, object]) -> httpx.Response:
        async with self._client() as client:
            response = await client.post(_mcp_url(self.base_url), json=payload)
            response.raise_for_status()
            return response

    def _parse_records(self, payload: dict[str, object]) -> list[MemoryRecord]:
        result = payload.get("result")
        if not isinstance(result, dict):
            return []

        content = result.get("content")
        if isinstance(content, list):
            return [
                MemoryRecord(content=str(item), source="graphiti", metadata={"raw": item})
                for item in content
            ]
        return []


@dataclass
class _BorrowedAsyncClient:
    client: httpx.AsyncClient

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


@dataclass
class MockLongTermMemoryClient:
    """In-memory client for tests and fallback behavior."""

    records: list[MemoryRecord] = field(default_factory=list)
    available: bool = True
    write_error: str | None = None
    search_error: str | None = None

    async def health(self) -> bool:
        """Return configured availability."""
        return self.available

    async def search(self, query: str, *, limit: int = 5) -> MemorySearchResult:
        """Search in-memory records."""
        if self.search_error:
            return MemorySearchResult(
                records=[],
                backend="mock",
                error=self.search_error,
            )
        lowered = query.lower()
        matches = [
            record
            for record in self.records
            if lowered in record.content.lower()
        ][:limit]
        return MemorySearchResult(records=matches, backend="mock")

    async def write(self, memory: MemoryWrite) -> MemoryWriteResult:
        """Write an in-memory record or report a configured failure."""
        if self.write_error:
            return MemoryWriteResult(
                status="skipped",
                backend="mock",
                error=self.write_error,
            )
        self.records.append(
            MemoryRecord(
                content=memory.content,
                source=memory.source,
                metadata=memory.metadata,
            )
        )
        return MemoryWriteResult(status="stored", backend="mock")


def create_graphiti_client(config: AppConfig | None = None) -> GraphitiMemoryClient:
    """Create the local Graphiti client without connecting to the service."""
    config = load_config() if config is None else config
    return GraphitiMemoryClient(
        base_url=config.graphiti_mcp_url,
        backend=config.graphiti_backend,
    )
