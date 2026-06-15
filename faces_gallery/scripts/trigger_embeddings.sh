#!/usr/bin/env bash
set -euo pipefail

HOST="${FACE_SYNC_HOST:-robiotec@10.0.0.2}"
SERVICE="${FACE_EMBEDDINGS_SERVICE:-robiotec-face-embeddings}"

if [[ -z "${SSHPASS:-}" ]]; then
  echo "ERROR: define SSHPASS antes de ejecutar este script."
  exit 1
fi

export SSHPASS
SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"

echo "Lanzando ${SERVICE}.service en $HOST"
$SSH_CMD "$HOST" "sudo systemctl start ${SERVICE}.service"

if [[ "${1:-}" == "--follow" ]]; then
  $SSH_CMD "$HOST" "sudo journalctl -u $SERVICE --no-pager -f -n 30"
fi
