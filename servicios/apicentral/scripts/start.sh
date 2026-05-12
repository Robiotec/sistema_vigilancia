#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
APP_DIR="$ROOT_DIR/apicentral"
LOG_DIR="$ROOT_DIR/servicios/apicentral/logs"
UV_BIN="${UV_BIN:-/root/.local/bin/uv}"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

exec "$UV_BIN" run uvicorn app.main:app --host 0.0.0.0 --port 8003
