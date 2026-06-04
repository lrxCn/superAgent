"""Graphiti long-term memory client boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent.config import DEFAULT_USER_ID, AppConfig, load_config


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
    group_id: str | None = None
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

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        group_id: str | None = None,
    ) -> MemorySearchResult:
        """Search long-term memory."""

    async def write(self, memory: MemoryWrite) -> MemoryWriteResult:
        """Write long-term memory."""


class GraphitiMemoryError(RuntimeError):
    """Raise when a Graphiti call fails unexpectedly."""


def _mcp_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/mcp"


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

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        group_id: str | None = None,
    ) -> MemorySearchResult:
        """Search Graphiti via MCP, falling back to an empty result."""
        arguments: dict[str, object] = {"query": query, "max_nodes": limit}
        if group_id:
            arguments["group_ids"] = [group_id]
        try:
            if self.http_client is not None:
                payload = _tool_call_payload(
                    request_id="superagent-memory-search",
                    name="search_nodes",
                    arguments=arguments,
                )
                records = self._parse_records((await self._post_mcp(payload)).json())
            else:
                result = await self._call_mcp_tool("search_nodes", arguments)
                records = self._parse_tool_records(result.content)
            return MemorySearchResult(records=records, backend=self.backend)
        except Exception as exc:
            return MemorySearchResult(records=[], backend=self.backend, error=str(exc))

    async def write(self, memory: MemoryWrite) -> MemoryWriteResult:
        """Write Graphiti episode via MCP, falling back to skipped."""
        arguments: dict[str, object] = {
            "name": memory.source,
            "episode_body": memory.content,
            "source": "text",
            "source_description": "SuperAgent long-term memory",
        }
        if memory.group_id:
            arguments["group_id"] = memory.group_id
        try:
            if self.http_client is not None:
                payload = _tool_call_payload(
                    request_id="superagent-memory-write",
                    name="add_memory",
                    arguments=arguments,
                )
                await self._post_mcp(payload)
            else:
                result = await self._call_mcp_tool("add_memory", arguments)
                if result.isError:
                    return MemoryWriteResult(
                        status="skipped",
                        backend=self.backend,
                        error=str(result.content),
                    )
            return MemoryWriteResult(status="stored", backend=self.backend)
        except Exception as exc:
            return MemoryWriteResult(status="skipped", backend=self.backend, error=str(exc))

    def _client(self):
        if self.http_client is not None:
            return _BorrowedAsyncClient(self.http_client)
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    async def _post_mcp(self, payload: dict[str, object]) -> httpx.Response:
        async with self._client() as client:
            response = await client.post(
                _mcp_url(self.base_url),
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
            )
            response.raise_for_status()
            return response

    async def _call_mcp_tool(self, name: str, arguments: dict[str, object]):
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as http_client:
            transport_context = streamable_http_client(
                _mcp_url(self.base_url),
                http_client=http_client,
            )
            read_stream, write_stream, _get_session_id = (
                await transport_context.__aenter__()
            )
            session_context = ClientSession(read_stream, write_stream)
            session = await session_context.__aenter__()
            try:
                await session.initialize()
                return await session.call_tool(name, arguments)
            finally:
                await session_context.__aexit__(None, None, None)
                await transport_context.__aexit__(None, None, None)

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

    def _parse_tool_records(self, content: object) -> list[MemoryRecord]:
        if not content:
            return []
        records: list[MemoryRecord] = []
        for item in content if isinstance(content, list) else [content]:
            text = getattr(item, "text", None)
            raw = text if text is not None else item
            records.append(
                MemoryRecord(
                    content=str(raw),
                    source="graphiti",
                    metadata={"raw": raw},
                )
            )
        return records


def _tool_call_payload(
    *,
    request_id: str,
    name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


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

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        group_id: str | None = None,
    ) -> MemorySearchResult:
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
            and _record_matches_group(record, group_id)
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
                metadata=_memory_metadata(memory),
            )
        )
        return MemoryWriteResult(status="stored", backend="mock")


def _record_matches_group(record: MemoryRecord, group_id: str | None) -> bool:
    if not group_id:
        return True
    record_group = record.metadata.get("group_id", DEFAULT_USER_ID)
    return record_group == group_id


def _memory_metadata(memory: MemoryWrite) -> dict[str, object]:
    if not memory.group_id:
        return dict(memory.metadata)
    return {**memory.metadata, "group_id": memory.group_id}


def create_graphiti_client(config: AppConfig | None = None) -> GraphitiMemoryClient:
    """Create the local Graphiti client without connecting to the service."""
    config = load_config() if config is None else config
    return GraphitiMemoryClient(
        base_url=config.graphiti_mcp_url,
        backend=config.graphiti_backend,
    )
