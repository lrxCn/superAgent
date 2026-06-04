# Graphiti OrbStack Runbook

This runbook is for the local Graphiti long-term memory service used by SuperAgent. SuperAgent talks to the Graphiti MCP HTTP endpoint; it must still degrade gracefully when this service is unavailable.

## Runtime Contract

SuperAgent expects the Graphiti MCP Server to run on OrbStack/Docker with the FalkorDB backend:

```dotenv
GRAPHITI_BACKEND=falkordb
GRAPHITI_MCP_URL=http://localhost:8000
FALKORDB_URL=redis://localhost:6379
```

Expected local endpoints:

| Service | Endpoint |
|---------|----------|
| Graphiti MCP HTTP | `http://localhost:8000/mcp` |
| Graphiti health | `http://localhost:8000/health` |
| FalkorDB Redis | `localhost:6379` |
| FalkorDB browser | `http://localhost:3000` |

## Prerequisites

- OrbStack is running.
- Docker Compose works from the terminal: `docker compose version`.
- A local Graphiti `.env` contains an LLM provider API key. The default Graphiti MCP configuration uses OpenAI-compatible LLM and embedding settings; use a real local secret file, never commit it.
- SuperAgent dependencies are installed: `uv sync --dev`.

## Start Graphiti From the Official Image

Prefer the official published image when Docker Hub is reachable. This avoids keeping a local Graphiti source checkout just to run the service.

```bash
docker pull zepai/knowledge-graph-mcp:latest
mkdir -p ~/.local/share/superagent/graphiti-config
```

Create `~/.local/share/superagent/graphiti-config/config.yaml`:

```yaml
server:
  transport: "http"
  host: "0.0.0.0"
  port: 8000

llm:
  provider: "openai"
  model: "gpt-4o-mini"
  max_tokens: 1024
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      api_url: ${OPENAI_API_URL:https://api.openai.com/v1}
      organization_id: ${OPENAI_ORGANIZATION_ID:}

embedder:
  provider: "openai"
  model: "text-embedding-3-small"
  dimensions: 1536
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      api_url: ${OPENAI_API_URL:https://api.openai.com/v1}
      organization_id: ${OPENAI_ORGANIZATION_ID:}

database:
  provider: "falkordb"
  providers:
    falkordb:
      uri: ${FALKORDB_URI:redis://localhost:6379}
      password: ${FALKORDB_PASSWORD:}
      database: ${FALKORDB_DATABASE:default_db}

graphiti:
  group_id: ${GRAPHITI_GROUP_ID:main}
  episode_id_prefix: ${EPISODE_ID_PREFIX:}
  user_id: ${USER_ID:mcp_user}
```

Start the combined FalkorDB + Graphiti MCP container. This example reuses SuperAgent's `.env` values without printing secrets:

```bash
OPENAI_API_KEY=$(awk -F= '/^OPENAI_API_KEY=/ {print substr($0, length("OPENAI_API_KEY=")+1)}' .env)
OPENAI_BASE_URL=$(awk -F= '/^OPENAI_BASE_URL=/ {print substr($0, length("OPENAI_BASE_URL=")+1)}' .env)

docker run -d \
  --name superagent-graphiti \
  -p 6379:6379 \
  -p 3000:3000 \
  -p 8000:8000 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e OPENAI_API_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}" \
  -e GRAPHITI_GROUP_ID=main \
  -e SEMAPHORE_LIMIT=10 \
  -e FALKORDB_PASSWORD= \
  -v superagent-graphiti-data:/var/lib/falkordb/data \
  -v "$HOME/.local/share/superagent/graphiti-config/config.yaml:/app/mcp/config/config.yaml:ro" \
  zepai/knowledge-graph-mcp:latest
```

If the container already exists:

```bash
docker start superagent-graphiti
```

Confirm the stack:

```bash
docker ps --filter name=superagent-graphiti
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/mcp >/dev/null || true
```

`/mcp` may not return a friendly body to `curl`; the health endpoint is the reliable readiness check.

## SiliconFlow-Compatible Local Setup

For SiliconFlow, use models that exist on the provider and keep embedding dimensions aligned. This local setup has been validated with:

```yaml
llm:
  provider: "openai"
  model: "Qwen/Qwen2.5-72B-Instruct"
  max_tokens: 1024
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      api_url: ${OPENAI_API_URL:https://api.siliconflow.cn/v1}

embedder:
  provider: "openai"
  model: "BAAI/bge-m3"
  dimensions: 1024
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      api_url: ${OPENAI_API_URL:https://api.siliconflow.cn/v1}
```

The observed `zepai/knowledge-graph-mcp:latest` image on 2026-06-04 needed two local compatibility fixes for OpenAI-compatible providers:

- use Graphiti's chat-completions client instead of the OpenAI Responses API client;
- pass the configured `api_url` into the LLM client, not only the embedder client.

Patch the running container before restart:

```bash
docker exec -i superagent-graphiti sh -s <<'SH'
python3 - <<'PY'
from pathlib import Path

path = Path("/app/mcp/src/services/factories.py")
text = path.read_text()

if "openai_generic_client import OpenAIGenericClient" not in text:
    text = text.replace(
        "from graphiti_core.llm_client import LLMClient, OpenAIClient",
        "from graphiti_core.llm_client import LLMClient, OpenAIClient\n"
        "from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient",
    )
text = text.replace(
    "return OpenAIClient(config=llm_config, reasoning='minimal', verbosity='low')",
    "return OpenAIGenericClient(config=llm_config, max_tokens=config.max_tokens)",
)
text = text.replace(
    "return OpenAIClient(config=llm_config, reasoning=None, verbosity=None)",
    "return OpenAIGenericClient(config=llm_config, max_tokens=config.max_tokens)",
)
text = text.replace(
    "                llm_config = CoreLLMConfig(\n"
    "                    api_key=api_key,\n"
    "                    model=config.model,\n",
    "                llm_config = CoreLLMConfig(\n"
    "                    api_key=api_key,\n"
    "                    base_url=config.providers.openai.api_url,\n"
    "                    model=config.model,\n",
)

path.write_text(text)
print("patched Graphiti OpenAI-compatible LLM client")
PY
SH

docker restart superagent-graphiti
curl -sf http://localhost:8000/health
```

This is a local container patch. It survives `docker restart`, but not `docker rm`; for repeated team usage, build a tiny custom image that applies the same patch during image build.

## Official Compose Fallback

If the published image is unavailable or you need to rebuild Graphiti locally, use the official source compose outside this repo:

```bash
mkdir -p ~/.local/share/superagent
cd ~/.local/share/superagent

git clone https://github.com/getzep/graphiti.git
cd graphiti/mcp_server
docker compose -f docker/docker-compose.yml up -d
```

## Configure SuperAgent

In this repo, keep `.env` aligned with `.env_example`:

```dotenv
GRAPHITI_BACKEND=falkordb
GRAPHITI_MCP_URL=http://localhost:8000
FALKORDB_URL=redis://localhost:6379
```

`src/agent/memory/graphiti.py` calls these MCP tools:

| SuperAgent method | Graphiti MCP tool |
|-------------------|-------------------|
| `health()` | `GET /health`, fallback `get_status` |
| `write(...)` | `add_memory` |
| `search(...)` | `search_nodes` |

## Smoke Test

Run the service-backed integration test only after health is green:

```bash
curl -sf http://localhost:8000/health
RUN_GRAPHITI_TESTS=true uv run pytest tests/integration_tests/test_graphiti_memory.py -q
```

Expected result:

```text
1 passed
```

Manual write/search demo:

```bash
uv run python - <<'PY'
import asyncio

from agent.memory.graphiti import MemoryWrite, create_graphiti_client


async def main() -> None:
    client = create_graphiti_client()
    print("health:", await client.health())
    print(
        "write:",
        await client.write(
            MemoryWrite(
                content=(
                    "用户 liurixing 的解释偏好：使用中文，回答要简洁直接；"
                    "解释 agent 工程问题时先讲清原因，再给可以执行的下一步。"
                ),
                source="manual-demo",
            )
        ),
    )
    await asyncio.sleep(65)
    result = await client.search("liurixing 喜欢什么解释方式？", limit=5)
    print("search error:", result.error)
    for record in result.records:
        print(record.content)


asyncio.run(main())
PY
```

## Stop and Reset

Stop containers without deleting data:

```bash
docker stop superagent-graphiti
```

Reset local graph data:

```bash
docker rm -f superagent-graphiti
docker volume rm superagent-graphiti-data
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `curl -sf http://localhost:8000/health` fails | `docker ps --filter name=superagent-graphiti`, `docker logs --tail=100 superagent-graphiti` |
| Port conflict on `8000`, `6379`, or `3000` | `lsof -nP -iTCP:8000 -sTCP:LISTEN`, then stop the conflicting local service |
| `add_memory` fails but health passes | Check the Graphiti `.env` LLM provider key and provider limits |
| `write(...)` returns `stored` but search finds no nodes | Check `docker logs --tail=200 superagent-graphiti`; the async queue may still be processing, or the LLM extraction call failed |
| SiliconFlow error says model does not exist | Update `llm.model`, `embedder.model`, and `embedder.dimensions` in the mounted config to provider-supported values |
| Logs show requests to `/responses` or LLM request timeouts | Apply the SiliconFlow-compatible local patch above and confirm logs show `/chat/completions` plus `https://api.siliconflow.cn/v1/embeddings` |
| Integration test skips | Confirm `RUN_GRAPHITI_TESTS=true` is set in the same command |
| SuperAgent writes are skipped | Check `GRAPHITI_MCP_URL`, then inspect `runtime_events` for memory write errors |
