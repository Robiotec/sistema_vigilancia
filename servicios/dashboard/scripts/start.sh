#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
APP_DIR="$ROOT_DIR/dashboard"
LOG_DIR="$ROOT_DIR/servicios/dashboard/logs"
UVICORN_BIN="${UVICORN_BIN:-$APP_DIR/.venv/bin/uvicorn}"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

exec "$UVICORN_BIN" app.main:app --host 0.0.0.0 --port 8010
