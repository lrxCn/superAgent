# Graphiti OrbStack Runbook

This runbook is for the optional local Graphiti long-term memory service. Task 05 does not require the service to be running; SuperAgent must fall back to no long-term memory when Graphiti is unavailable.

## Defaults

SuperAgent expects the first-phase Graphiti deployment to use the Graphiti MCP Server with the FalkorDB backend on local Docker/OrbStack.

```dotenv
GRAPHITI_BACKEND=falkordb
GRAPHITI_MCP_URL=http://localhost:8000
FALKORDB_URL=redis://localhost:6379
```

The Graphiti MCP HTTP endpoint is expected at:

```text
http://localhost:8000/mcp/
```

The health endpoint is expected at:

```text
http://localhost:8000/health
```

## Local Startup

1. Start OrbStack.
2. Use the Graphiti MCP Server Docker Compose setup with FalkorDB.
3. Confirm containers are running:

```bash
docker compose ps
```

4. Confirm the service is reachable:

```bash
curl http://localhost:8000/health
```

5. Run the optional smoke test:

```bash
RUN_GRAPHITI_TESTS=true uv run pytest tests/integration_tests -m graphiti
```

If the service is not running, the optional smoke test skips and normal unit tests still pass.
