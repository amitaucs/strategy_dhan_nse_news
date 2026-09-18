#!/usr/bin/env bash
# ==============================================================================
# Docker Management Helper for NSE Unified Trading Platform
# Usage:
#   ./infra/deploy/docker.sh up [-d] [-p PORT] [--build]
#   ./infra/deploy/docker.sh down
#   ./infra/deploy/docker.sh restart [-d] [-p PORT]
#   ./infra/deploy/docker.sh logs [-f] [--tail N]
#   ./infra/deploy/docker.sh ps
#   ./infra/deploy/docker.sh shell
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker/docker-compose.yml"

# Default port if not provided
DEFAULT_PORT=8000
PORT="${PORT:-$DEFAULT_PORT}"

show_help() {
  cat << EOF
NSE Unified Trading Platform - Docker Controller

Usage:
  $(basename "$0") <command> [options]

Commands:
  up          Start the container (foreground or detached)
  down|stop   Stop and remove the running container
  restart     Restart the container
  logs        View / follow container logs in real time
  ps|status   Check container status and health
  shell       Open an interactive shell inside the container
  help        Show this help message

Options for 'up' / 'restart':
  -d, --detach        Run container in the background (detached mode)
  -p, --port <PORT>   Specify host port mapping (default: 8000)
  -b, --build         Force rebuild the Docker image before starting

Examples:
  # Start in background on default port 8000
  ./infra/deploy/docker.sh up -d

  # Start in background on custom port with rebuild
  ./infra/deploy/docker.sh up -d -p 8000 --build

  # View live streaming logs
  ./infra/deploy/docker.sh logs

  # Stop container
  ./infra/deploy/docker.sh down
EOF
}

COMMAND="$1"
shift || true

case "$COMMAND" in
  up)
    DETACH=""
    BUILD=""
    EXTRA_ARGS=()

    while [[ $# -gt 0 ]]; do
      case "$1" in
        -d|--detach)
          DETACH="-d"
          shift
          ;;
        -p|--port)
          PORT="$2"
          shift 2
          ;;
        -b|--build)
          BUILD="--build"
          shift
          ;;
        *)
          EXTRA_ARGS+=("$1")
          shift
          ;;
      esac
    done

    echo "🚀 Starting NSE Trading Platform on host port ${PORT}..."
    if [[ -n "$DETACH" ]]; then
      echo "ℹ️  Running in background (detached mode)."
    else
      echo "ℹ️  Running in foreground. Console logs will stream below (Ctrl+C to exit):"
    fi

    PORT="$PORT" docker compose -f "$COMPOSE_FILE" up $DETACH $BUILD "${EXTRA_ARGS[@]}"

    if [[ -n "$DETACH" ]]; then
      echo "✅ Container started successfully!"
      echo "🌐 Web Dashboard: http://localhost:${PORT}"
      echo "📜 View live logs: ./infra/deploy/docker.sh logs"
    fi
    ;;

  down|stop)
    echo "🛑 Stopping NSE Trading Platform..."
    docker compose -f "$COMPOSE_FILE" down "$@"
    echo "✅ Container stopped."
    ;;

  restart)
    DETACH=""
    BUILD=""
    EXTRA_ARGS=()

    while [[ $# -gt 0 ]]; do
      case "$1" in
        -d|--detach)
          DETACH="-d"
          shift
          ;;
        -p|--port)
          PORT="$2"
          shift 2
          ;;
        -b|--build)
          BUILD="--build"
          shift
          ;;
        *)
          EXTRA_ARGS+=("$1")
          shift
          ;;
      esac
    done

    echo "🔄 Restarting container on port ${PORT}..."
    docker compose -f "$COMPOSE_FILE" down
    PORT="$PORT" docker compose -f "$COMPOSE_FILE" up $DETACH $BUILD "${EXTRA_ARGS[@]}"
    ;;

  logs)
    docker compose -f "$COMPOSE_FILE" logs -f "$@"
    ;;

  ps|status)
    docker compose -f "$COMPOSE_FILE" ps "$@"
    ;;

  shell|bash)
    echo "🐚 Opening shell in running container..."
    docker exec -it nse_catalyst_terminal /bin/bash
    ;;

  help|--help|-h|"")
    show_help
    ;;

  *)
    echo "❌ Unknown command: $COMMAND"
    echo ""
    show_help
    exit 1
    ;;
esac

