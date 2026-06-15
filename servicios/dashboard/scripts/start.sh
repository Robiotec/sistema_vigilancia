#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
APP_DIR="$ROOT_DIR/dashboard"
LOG_DIR="$ROOT_DIR/servicios/dashboard/logs"
UVICORN_BIN="${UVICORN_BIN:-$APP_DIR/.venv/bin/uvicorn}"
ENV_FILE="$APP_DIR/.env"

read_env_value() {
  key="$1"
  if [ -f "$ENV_FILE" ]; then
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$ENV_FILE" | tr -d '\r'
  fi
}

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

DASHBOARD_HOST="${DASHBOARD_HOST:-$(read_env_value DASHBOARD_HOST)}"
DASHBOARD_PORT="${DASHBOARD_PORT:-$(read_env_value DASHBOARD_PORT)}"

exec "$UVICORN_BIN" app.main:app --host "${DASHBOARD_HOST:-127.0.0.1}" --port "${DASHBOARD_PORT:-8010}"
