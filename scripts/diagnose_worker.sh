#!/usr/bin/env bash
set -euo pipefail

WORKER_NAME="${WORKER_NAME:-wsai_news_worker}"
BACKEND_IMAGE="${BACKEND_IMAGE:-wsai_backend:latest}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "[PASS] $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "[FAIL] $1"
}

step() {
  echo
  echo "==> $1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run_check() {
  local label="$1"
  shift
  if "$@"; then
    pass "$label"
  else
    fail "$label"
  fi
}

check_required_tools() {
  local missing=0
  for cmd in docker; do
    if ! has_cmd "$cmd"; then
      echo "missing command: $cmd"
      missing=1
    fi
  done

  if ! docker compose version >/dev/null 2>&1; then
    echo "missing command: docker compose plugin"
    missing=1
  fi

  return "$missing"
}

check_docker_daemon_access() {
  docker info >/dev/null 2>&1
}

check_worker_exists() {
  docker ps -a --format '{{.Names}}' | grep -Fxq "$WORKER_NAME"
}

check_worker_running() {
  local state
  state="$(docker inspect "$WORKER_NAME" --format '{{.State.Status}}' 2>/dev/null || true)"
  [[ "$state" == "running" ]]
}

check_worker_has_env() {
  docker inspect "$WORKER_NAME" --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep -q '^JWT_SECRET='
}

check_compose_has_worker_jwt() {
  [[ -f "$COMPOSE_FILE" ]] || return 1
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config 2>/dev/null \
    | awk '/news_worker:/{in_worker=1} in_worker{print} /^[^[:space:]]/{if ($0 !~ /^news_worker:/) in_worker=0}' \
    | grep -q 'JWT_SECRET:'
}

check_env_file_has_jwt() {
  [[ -f "$ENV_FILE" ]] || return 1
  grep -Eq '^JWT_SECRET=.+$' "$ENV_FILE"
}

check_settings_import_with_env() {
  local db_url="${DATABASE_URL:-}"
  if [[ -z "$db_url" ]]; then
    local pg_user pg_pass pg_db
    pg_user="${POSTGRES_USER:-wsai}"
    pg_pass="${POSTGRES_PASSWORD:-}"
    pg_db="${POSTGRES_DB:-wsai}"
    if [[ -n "$pg_pass" ]]; then
      db_url="postgresql+psycopg://${pg_user}:${pg_pass}@postgres:5432/${pg_db}"
    fi
  fi

  if [[ -z "$db_url" ]]; then
    # Attempt to load values from .env if they are not exported in shell.
    local env_pg_user env_pg_pass env_pg_db env_db_url
    env_pg_user="$(grep -E '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    env_pg_pass="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    env_pg_db="$(grep -E '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    env_db_url="$(grep -E '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
    if [[ -n "$env_db_url" ]]; then
      db_url="$env_db_url"
    elif [[ -n "$env_pg_pass" ]]; then
      db_url="postgresql+psycopg://${env_pg_user:-wsai}:${env_pg_pass}@postgres:5432/${env_pg_db:-wsai}"
    fi
  fi

  [[ -n "$db_url" ]] || return 1

  docker run --rm --env-file "$ENV_FILE" -e "DATABASE_URL=$db_url" "$BACKEND_IMAGE" \
    python -c "from app.core.config import settings; print('settings-ok')" >/dev/null
}

check_worker_logs_for_jwt_error() {
  local logs
  logs="$(docker logs --tail 200 "$WORKER_NAME" 2>&1)" || return 1
  ! printf '%s\n' "$logs" | grep -q 'JWT_SECRET'
}

check_worker_db_connectivity() {
  docker exec "$WORKER_NAME" sh -lc '
    getent hosts postgres >/dev/null &&
    python - <<'"'"'PY'"'"'
import socket
s = socket.create_connection(("postgres", 5432), timeout=3)
s.close()
PY
  '
}

print_hints() {
  echo
  echo "Suggested actions for failures:"
  echo "1. Ensure $ENV_FILE contains JWT_SECRET with at least 32 chars."
  echo "2. Ensure POSTGRES_PASSWORD exists in $ENV_FILE (or set DATABASE_URL explicitly)."
  echo "3. Ensure news_worker gets JWT_SECRET in $COMPOSE_FILE."
  echo "4. Recreate worker: docker compose up -d --build news_worker"
  echo "5. If compose is run outside project dir, pass explicit -f and --env-file."
}

main() {
  step "Preflight"
  run_check "required tools installed (docker + docker compose)" check_required_tools
  run_check "docker daemon is accessible" check_docker_daemon_access
  run_check "env file exists and has JWT_SECRET" check_env_file_has_jwt
  run_check "compose resolves news_worker with JWT_SECRET" check_compose_has_worker_jwt

  step "Container checks"
  run_check "worker container exists" check_worker_exists
  run_check "worker container is running" check_worker_running
  run_check "worker container has JWT_SECRET env" check_worker_has_env
  run_check "worker logs do not show JWT_SECRET startup error" check_worker_logs_for_jwt_error

  step "Image and runtime checks"
  run_check "backend image can import app settings with env file" check_settings_import_with_env
  run_check "worker can resolve/reach postgres:5432 from container" check_worker_db_connectivity

  echo
  echo "Summary: pass=$PASS_COUNT fail=$FAIL_COUNT"
  if [[ "$FAIL_COUNT" -gt 0 ]]; then
    print_hints
    exit 1
  fi
}

main "$@"
