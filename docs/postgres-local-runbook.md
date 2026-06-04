# PostgreSQL Local Runbook

This runbook is for the optional PostgreSQL checkpointer used by SuperAgent short-term memory. The default `langgraph dev` graph still uses the in-memory checkpointer; PostgreSQL is enabled through the explicit checkpointer factory path.

## Runtime Contract

SuperAgent reads these variables from `.env`:

```dotenv
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable
CHECKPOINT_SETUP=true
```

`CHECKPOINT_SETUP=true` makes `create_postgres_checkpointer()` call `AsyncPostgresSaver.setup()` on startup so the LangGraph checkpoint tables exist.

## Start PostgreSQL

Start OrbStack, then run a local `postgres:16` container:

```bash
docker run -d \
  --name superagent-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=super_agent \
  -p 5432:5432 \
  -v superagent-postgres-data:/var/lib/postgresql/data \
  postgres:16
```

Use `postgres:16` for this runbook. `postgres:latest` may resolve to PostgreSQL 18+, whose default `PGDATA` path is versioned under `/var/lib/postgresql/18/docker`; with the `/var/lib/postgresql/data` mount shown above, that image can exit immediately with a data-directory layout error.

Confirm readiness:

```bash
docker exec superagent-postgres pg_isready -U postgres -d super_agent
```

If the container already exists:

```bash
docker start superagent-postgres
docker exec superagent-postgres pg_isready -U postgres -d super_agent
```

## Configure SuperAgent

In this repo, keep `.env` aligned with `.env_example`:

```dotenv
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable
CHECKPOINT_SETUP=true
```

Do not commit `.env`.

## Use the Checkpointer

`langgraph.json` exposes:

```json
"agent": "./src/agent/graph.py:graph"
```

That default graph is compiled by `graph = build_graph()` and uses the in-memory checkpointer. It is the default local Studio path.

For PostgreSQL-backed local runs, use the explicit factory from `src/agent/graph.py`:

```python
from agent.graph import create_graph_with_checkpointer

graph, resource = await create_graph_with_checkpointer()
try:
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "checkpoint test"}]},
        config={"configurable": {"thread_id": "local-postgres-thread"}},
    )
finally:
    await resource.aclose()
```

Tests use the same contract through `create_postgres_checkpointer()` and `build_graph(checkpointer=...)`. If PostgreSQL is unreachable, the factory falls back to an in-memory checkpointer and records the fallback reason.

## Smoke Test

Run the service-backed integration test only after `pg_isready` is green:

```bash
docker exec superagent-postgres pg_isready -U postgres -d super_agent
RUN_POSTGRES_TESTS=true uv run pytest tests/integration_tests/test_postgres_checkpoint.py -q
```

Expected result:

```text
1 passed
```

## Stop and Reset

Stop PostgreSQL without deleting checkpoint data:

```bash
docker stop superagent-postgres
```

Reset local checkpoint data:

```bash
docker rm -f superagent-postgres
docker volume rm superagent-postgres-data
docker run -d \
  --name superagent-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=super_agent \
  -p 5432:5432 \
  -v superagent-postgres-data:/var/lib/postgresql/data \
  postgres:16
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `docker run` says container name is in use | Use `docker start superagent-postgres` or remove the old container intentionally |
| `pg_isready` fails | Check `docker logs --tail=100 superagent-postgres` |
| Port `5432` is in use | `lsof -nP -iTCP:5432 -sTCP:LISTEN`, then either stop the conflict or map Postgres to another host port and update `DATABASE_URL` |
| `postgres:latest` exits with a PostgreSQL 18 data directory warning | Use `postgres:16`, or mount PostgreSQL 18 at `/var/lib/postgresql` instead of `/var/lib/postgresql/data` |
| Integration test skips | Confirm `RUN_POSTGRES_TESTS=true` and `DATABASE_URL` are set in the same shell |
| Factory falls back to memory | Inspect `resource.fallback_reason`; common causes are wrong password, wrong database name, or port conflict |
