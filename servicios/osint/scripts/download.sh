#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
OSINT_DIR="$ROOT_DIR/osint"
LOG_DIR="$ROOT_DIR/servicios/osint/logs"
UV_BIN="${UV_BIN:-/root/.local/bin/uv}"

mkdir -p "$LOG_DIR"
cd "$OSINT_DIR"

{
  echo "[$(date -Is)] Iniciando descarga OSINT"
  OSINT_OUT_DIR="${OSINT_OUT_DIR:-$OSINT_DIR}" \
    "$UV_BIN" run --with requests python "$OSINT_DIR/download_osint.py"
  echo "[$(date -Is)] Descarga OSINT finalizada"
} >> "$LOG_DIR/osint-download.log" 2>&1
