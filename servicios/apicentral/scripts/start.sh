#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
APP_DIR="$ROOT_DIR/apicentral"
LOG_DIR="$ROOT_DIR/servicios/apicentral/logs"
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

API_HOST="${API_HOST:-$(read_env_value API_HOST)}"
API_PORT="${API_PORT:-$(read_env_value API_PORT)}"

exec "$UVICORN_BIN" app.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8003}"
