#!/usr/bin/env bash
# Helper script to manage ST15_LargeCap Docker container
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/infra/docker/docker-compose.yml"

case "${1:-up}" in
  up)
    shift || true
    echo "🚀 Starting ST15_LargeCap Terminal on port 8015..."
    docker compose -f "$COMPOSE_FILE" up -d "$@"
    ;;
  down)
    shift || true
    echo "🛑 Stopping ST15_LargeCap Terminal..."
    docker compose -f "$COMPOSE_FILE" down "$@"
    ;;
  restart)
    shift || true
    echo "🔄 Restarting ST15_LargeCap Terminal..."
    docker compose -f "$COMPOSE_FILE" restart "$@"
    ;;
  logs)
    shift || true
    docker compose -f "$COMPOSE_FILE" logs -f "$@"
    ;;
  ps)
    docker compose -f "$COMPOSE_FILE" ps
    ;;
  *)
    docker compose -f "$COMPOSE_FILE" "$@"
    ;;
esac

