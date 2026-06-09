#!/usr/bin/env bash
# pull_logs.sh
# Descarga logs recientes de los servicios de rostros desde 10.0.0.2.
# Requiere: export SSHPASS=<password_robiotec>
# Uso: ./pull_logs.sh [--lines N]   (default N=200)
set -euo pipefail

HOST="robiotec@10.0.0.2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/../logs"
LINES="200"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --lines) LINES="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "${SSHPASS:-}" ]]; then
    echo "ERROR: Variable SSHPASS no definida. Ejecutar: export SSHPASS=<password>"
    exit 1
fi
export SSHPASS

SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
mkdir -p "$LOGS_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

for SERVICE in robiotec-face-sync robiotec-face-embeddings; do
    LOGFILE="$LOGS_DIR/${SERVICE}.log"
    echo "[$TS] Descargando $LINES líneas: $SERVICE ..."
    $SSH_CMD "$HOST" "journalctl -u $SERVICE --no-pager -n $LINES 2>&1" > "$LOGFILE"
    echo "  -> $(wc -l < "$LOGFILE") líneas en $LOGFILE"
done

echo "[$TS] Logs actualizados en $LOGS_DIR"
