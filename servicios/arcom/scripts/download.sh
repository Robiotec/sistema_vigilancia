#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
ARCOM_DIR="$ROOT_DIR/arcom"
LOG_DIR="$ROOT_DIR/servicios/arcom/logs"
UV_BIN="${UV_BIN:-/root/.local/bin/uv}"

mkdir -p "$LOG_DIR"
cd "$ARCOM_DIR"

{
  echo "[$(date -Is)] Iniciando descarga ARCOM"
  ARCOM_OUT_DIR="${ARCOM_OUT_DIR:-$ARCOM_DIR}" \
    "$UV_BIN" run --with requests python "$ARCOM_DIR/download_arcom.py"
  echo "[$(date -Is)] Descarga ARCOM finalizada"
} >> "$LOG_DIR/arcom-download.log" 2>&1
