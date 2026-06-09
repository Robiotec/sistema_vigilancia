#!/usr/bin/env bash
# trigger_sync.sh
# Lanza robiotec-face-sync.service en 10.0.0.2 y espera resultado.
# Requiere: export SSHPASS=<password_robiotec>
# Uso: ./trigger_sync.sh [--follow]
set -euo pipefail

HOST="robiotec@10.0.0.2"
SERVICE="robiotec-face-sync"
SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"

if [[ -z "${SSHPASS:-}" ]]; then
    echo "ERROR: Variable SSHPASS no definida. Ejecutar: export SSHPASS=<password>"
    exit 1
fi
export SSHPASS

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Lanzando $SERVICE en $HOST ..."
$SSH_CMD "$HOST" "sudo systemctl start ${SERVICE}.service"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Servicio iniciado"

if [[ "${1:-}" == "--follow" ]]; then
    echo "--- Logs en tiempo real ---"
    $SSH_CMD "$HOST" "sudo journalctl -u $SERVICE --no-pager -f -n 30"
fi
