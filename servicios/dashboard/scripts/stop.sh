#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
APP_DIR="$ROOT_DIR/dashboard"
ENV_FILE="$APP_DIR/.env"

read_env_value() {
  key="$1"
  if [ -f "$ENV_FILE" ]; then
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$ENV_FILE" | tr -d '\r'
  fi
}

DASHBOARD_PORT="${DASHBOARD_PORT:-$(read_env_value DASHBOARD_PORT)}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8010}"

pkill -f "uvicorn app.main:app .*--port ${DASHBOARD_PORT}" || true
