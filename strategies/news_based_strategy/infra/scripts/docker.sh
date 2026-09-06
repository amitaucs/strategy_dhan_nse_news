#!/usr/bin/env bash
# ==============================================================================
# Docker Management Helper for NSE Catalyst Trading Terminal
# Usage:
#   ./infra/scripts/docker.sh up [-d] [-p PORT] [--build]
#   ./infra/scripts/docker.sh down
#   ./infra/scripts/docker.sh restart [-d] [-p PORT]
#   ./infra/scripts/docker.sh logs [-f] [--tail N]
#   ./infra/scripts/docker.sh ps
#   ./infra/scripts/docker.sh poller
# ==============================================================================

set -e

# Resolve directories relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/infra/docker/docker-compose.yml"

# Default port if not provided
DEFAULT_PORT=8000
PORT="${PORT:-$DEFAULT_PORT}"

# Help menu
show_help() {
  cat << EOF
NSE Catalyst Trading Terminal - Docker Controller

Usage:
  $(basename "$0") <command> [options]

Commands:
  up          Start the container (foreground or detached)
  down|stop   Stop and remove the running container
  restart     Restart the container
  logs        View / follow container logs in real time
  ps|status   Check container status and health
  poller      Run pure CLI terminal poller interactively
  shell       Open an interactive shell inside the container
  help        Show this help message

Options for 'up' / 'restart':
  -d, --detach        Run container in the background (detached mode)
  -p, --port <PORT>   Specify host port mapping (default: 8000)
  -b, --build         Force rebuild the Docker image before starting

Examples:
  # Start in background on default port 8000
  ./infra/scripts/docker.sh up -d

  # Start in background on custom port 9000 with image rebuild
  ./infra/scripts/docker.sh up -d -p 9000 --build

  # Start in foreground (streaming logs directly to console)
  ./infra/scripts/docker.sh up -p 9000

  # View live streaming logs
  ./infra/scripts/docker.sh logs

  # Stop container
  ./infra/scripts/docker.sh down
EOF
}

# Main command dispatcher
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

    echo "🚀 Starting NSE Catalyst Trading Terminal on host port ${PORT}..."
    if [[ -n "$DETACH" ]]; then
      echo "ℹ️  Running in background (detached mode)."
    else
      echo "ℹ️  Running in foreground. Console logs will stream below (Ctrl+C to exit):"
    fi

    PORT="$PORT" docker compose -f "$COMPOSE_FILE" up $DETACH $BUILD "${EXTRA_ARGS[@]}"

    if [[ -n "$DETACH" ]]; then
      echo "✅ Container started successfully!"
      echo "🌐 Web Dashboard: http://localhost:${PORT}"
      echo "📜 View live logs: ./infra/scripts/docker.sh logs"
    fi
    ;;

  down|stop)
    echo "🛑 Stopping NSE Catalyst Trading Terminal..."
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

  poller)
    echo "📡 Running interactive CLI poller inside Docker..."
    cd "$PROJECT_ROOT"
    docker run -it --rm \
      --env-file .env \
      -v "${PROJECT_ROOT}/data:/app/data" \
      nse-catalyst-terminal \
      python3 -m news_based_strategy.main "$@"
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

