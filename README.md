# SuperAgent

SuperAgent is a LangGraph-based agent runtime for local `langgraph dev`. The repository currently contains a runnable state/config graph skeleton; the target architecture is documented in [docs/prd/super-agent-runtime-architecture.md](docs/prd/super-agent-runtime-architecture.md) and will be implemented through the task cards in [docs/prompts/](docs/prompts/).

## Current Status

| Item | Status |
|------|--------|
| Runtime code | Runnable state/config graph skeleton with SiliconFlow LLM adapter |
| Target runtime | Planned multi-path agent runtime |
| Core tasks | 03/15 completed |
| Progress | [docs/progress.md](docs/progress.md) |
| Source PRD | [docs/prd/super-agent-runtime-architecture.md](docs/prd/super-agent-runtime-architecture.md) |

## Documentation Order

1. `AGENTS.md`: local agent working rules.
2. `README.md`: current architecture and runtime contract.
3. `docs/progress.md`: task queue, status, dependencies, and changelog.
4. `docs/prompts/`: one executable implementation task per file.
5. `docs/prd/`: design intent, decisions, and historical rationale.
6. `docs/maps/`: architecture/code maps generated after implementation lands.

## Architecture

The target runtime starts with user input, loads memory, checks context budget, routes by task type and complexity, then chooses one of the execution paths below:

| Path | Purpose |
|------|---------|
| Direct answer | Low-risk requests that do not need tools or planning |
| ReAct tools | External or tool-backed work through MCP |
| Plan-and-Execute | Multi-step goals with explicit plan validation and step observations |
| Multi-Agent | Parallel worker execution for researcher/coder/reviewer/memory-manager roles |
| Reflection | Partially enabled quality gate for complex, tool, plan, multi-agent, high-risk, low-confidence, or user-requested review paths |
| Fallback | Clarification, partial result, safe refusal, or downgraded answer when execution cannot continue |

The implementation should keep LangGraph as the orchestration boundary. Nodes should exchange explicit state fields rather than ad hoc dictionaries that drift across tasks.

## Contracts

### Runtime

- First phase only targets local `langgraph dev`.
- Do not plan for LangGraph Platform deployment in the first phase.
- `langgraph.json` exposes the `agent` graph from `src/agent/graph.py`.

### LLM

- First real provider: SiliconFlow only.
- Use the OpenAI-compatible variable names retained from commonAgent:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL_NAME`
- Default model: `Pro/moonshotai/Kimi-K2.6`.
- Do not commit real API keys.

### Memory

- Short-term memory: LangGraph checkpoint + PostgreSQL.
- Checkpointer package: `langgraph-checkpoint-postgres`.
- First implementation should use `AsyncPostgresSaver.from_conn_string(DATABASE_URL)` and `setup()` for table initialization.
- Long-term memory: local Graphiti deployment, defaulting to the Graphiti MCP Server Docker Compose FalkorDB backend on OrbStack/Docker.

### Tools

- External tools are reached through MCP.
- Backend engineering will provide the real MCP server later.
- Until then, use the official filesystem MCP server only as a connectivity example:

```bash
npx -y @modelcontextprotocol/server-filesystem ./docs
```

### Multi-Agent

- First phase supports parallel worker orchestration.
- Defaults:
  - `WORKER_MAX_CONCURRENCY=4`
  - `WORKER_TIMEOUT_SECONDS=120`
- Worker timeout or exception is recorded as `failed`; aggregation returns `partial` without waiting past timeout.

### Reflection

- Reflection is partially enabled.
- Enable when:
  - route path is tool, plan, or multi-agent,
  - route confidence is below `0.72`,
  - fallback is about to run,
  - user explicitly asks for review/checking,
  - high-risk keyword/category rules match.
- Default `REFLECTION_MAX_ROUNDS=1`.

### Configuration

Non-secret defaults are tracked in both `.env_example` and `.env.example` for compatibility with different tooling conventions. Keep the two files identical; real keys belong only in local `.env`.

```dotenv
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=SUPER_AGENT
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL_NAME=Pro/moonshotai/Kimi-K2.6
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=4096

REACT_MAX_STEPS=8
PLAN_MAX_STEPS=12
WORKER_MAX_CONCURRENCY=4
WORKER_TIMEOUT_SECONDS=120
TOOL_TIMEOUT_SECONDS=30
REFLECTION_MAX_ROUNDS=1

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/super_agent?sslmode=disable
CHECKPOINT_SETUP=true

MCP_EXAMPLE_SERVER_COMMAND=npx
MCP_EXAMPLE_SERVER_ARGS=-y @modelcontextprotocol/server-filesystem ./docs
MCP_TOOL_TIMEOUT_SECONDS=30

GRAPHITI_BACKEND=falkordb
GRAPHITI_MCP_URL=http://localhost:8000
FALKORDB_URL=redis://localhost:6379
```

## Development Workflow

Use `uv` for Python environment and dependency management.

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
uv run langgraph dev
```

To execute implementation work, open one task card from `docs/prompts/` in a fresh agent window and follow its model/reasoning gate, dependency check, validation plan, progress update, and git commit rule.
