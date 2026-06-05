#!/usr/bin/env bash
# Start local OrbStack services (Postgres + Graphiti) and run langgraph dev.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

POSTGRES_CONTAINER="superagent-postgres"
GRAPHITI_CONTAINER="superagent-graphiti"

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

require_docker() {
  if ! docker info >/dev/null 2>&1; then
    die "Docker 未就绪，请先启动 OrbStack。"
  fi
}

container_exists() {
  docker ps -a --format '{{.Names}}' | grep -qx "$1"
}

start_container() {
  local name="$1"
  local runbook="$2"

  if container_exists "$name"; then
    log "启动容器 $name"
    docker start "$name" >/dev/null
    return
  fi

  die "容器 $name 不存在。请先按 $runbook 创建。"
}

wait_for_postgres() {
  log "等待 PostgreSQL 就绪"
  local i
  for i in $(seq 1 30); do
    if docker exec "$POSTGRES_CONTAINER" pg_isready -U postgres -d super_agent >/dev/null 2>&1; then
      log "PostgreSQL 已就绪"
      return
    fi
    sleep 1
  done
  die "PostgreSQL 启动超时，请检查: docker logs --tail=100 $POSTGRES_CONTAINER"
}

wait_for_graphiti() {
  log "等待 Graphiti 就绪 (http://localhost:8000/health)"
  local i
  for i in $(seq 1 90); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      log "Graphiti 已就绪"
      return
    fi
    sleep 1
  done
  die "Graphiti 启动超时，请检查: docker logs --tail=100 $GRAPHITI_CONTAINER"
}

main() {
  require_docker
  start_container "$POSTGRES_CONTAINER" "docs/postgres-local-runbook.md"
  start_container "$GRAPHITI_CONTAINER" "docs/graphiti-orbstack-runbook.md"
  wait_for_postgres
  wait_for_graphiti
  log "启动 langgraph dev（Ctrl+C 退出）"
  exec uv run langgraph dev
}

main "$@"
