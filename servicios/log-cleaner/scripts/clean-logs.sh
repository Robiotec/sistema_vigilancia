#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
SERVICES_DIR="$ROOT_DIR/servicios"
LOG_FILE="$SERVICES_DIR/log-cleaner/logs/log-cleaner.log"

mkdir -p "$SERVICES_DIR/log-cleaner/logs"

{
  echo "[$(date -Is)] Iniciando limpieza semanal de logs"
  find "$SERVICES_DIR" -path "*/logs/*.log" -type f ! -path "$LOG_FILE" -print -exec sh -c ': > "$1"' sh {} \;
  echo "[$(date -Is)] Limpieza semanal de logs finalizada"
} >> "$LOG_FILE" 2>&1
