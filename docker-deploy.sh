#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] Docker Compose v2 is required." >&2
  exit 1
fi

ensure_env() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "[ERROR] Created .env from .env.example. Set ANTHROPIC_API_KEY, then run again." >&2
    exit 1
  fi
}

health() {
  local app_port
  app_port="$(grep -E '^APP_PORT=' .env 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
  app_port="${app_port:-8080}"
  curl -fsS "http://127.0.0.1:${app_port}/healthz" >/dev/null
  curl -fsS "http://127.0.0.1:${app_port}/api/python/health" >/dev/null
  echo "[OK] Frontend gateway and backend API are healthy."
}

case "${1:-help}" in
  up)
    ensure_env
    docker compose up -d --build
    docker compose ps
    ;;
  down)
    docker compose down
    ;;
  restart)
    ensure_env
    docker compose up -d --build --force-recreate
    ;;
  status)
    docker compose ps
    ;;
  logs)
    shift || true
    docker compose logs -f "$@"
    ;;
  health)
    ensure_env
    health
    ;;
  config)
    ensure_env
    docker compose config
    ;;
  reset)
    echo "This deletes Redis, ChromaDB and Prometheus data volumes."
    read -r -p "Continue? [y/N] " answer
    [[ "$answer" =~ ^[Yy]$ ]] && docker compose down -v
    ;;
  *)
    cat <<'EOF'
Usage: ./docker-deploy.sh <command>

Commands:
  up        Build and start the complete stack
  down      Stop containers and preserve data volumes
  restart   Rebuild and recreate the complete stack
  status    Show container status
  logs      Follow logs; optionally pass service names
  health    Check frontend gateway and backend API
  config    Render and validate the Compose configuration
  reset     Stop the stack and delete persistent data volumes
EOF
    ;;
esac
