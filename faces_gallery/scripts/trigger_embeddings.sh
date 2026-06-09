#!/usr/bin/env bash
# trigger_embeddings.sh
# Lanza robiotec-face-embeddings.service en 10.0.0.2.
# Requiere: export SSHPASS=<password_robiotec>
# Uso: ./trigger_embeddings.sh [--follow] [--force]
set -euo pipefail

HOST="robiotec@10.0.0.2"
SERVICE="robiotec-face-embeddings"
VENV_PY="/home/robiotec/Documents/VICTOR/.venv/bin/python"
SCRIPT="/home/robiotec/Documents/ROSTROS_PERSONAL_SYNC/generate_embeddings.py"
SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"

if [[ -z "${SSHPASS:-}" ]]; then
    echo "ERROR: Variable SSHPASS no definida. Ejecutar: export SSHPASS=<password>"
    exit 1
fi
export SSHPASS

FORCE=""
FOLLOW=0
for arg in "$@"; do
    case "$arg" in
        --force)   FORCE="--force" ;;
        --follow)  FOLLOW=1 ;;
    esac
done

if [[ -n "$FORCE" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ejecutando con --force en $HOST ..."
    $SSH_CMD "$HOST" \
        "cd /home/robiotec/Documents/ROSTROS_PERSONAL_SYNC && \
         set -a && source /home/robiotec/Documents/VICTOR/Object_Recognition_v5/Object_Recognition/.env && set +a && \
         $VENV_PY $SCRIPT --force"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Lanzando $SERVICE en $HOST ..."
    $SSH_CMD "$HOST" "sudo systemctl start ${SERVICE}.service"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Servicio iniciado"
fi

if [[ "$FOLLOW" -eq 1 ]]; then
    echo "--- Logs en tiempo real ---"
    $SSH_CMD "$HOST" "sudo journalctl -u $SERVICE --no-pager -f -n 30"
fi
