#!/usr/bin/env bash
set -euo pipefail

HOST="${FACE_SYNC_HOST:-robiotec@10.0.0.2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/../logs"
LINES="${LINES:-200}"

if [[ -z "${SSHPASS:-}" ]]; then
  echo "ERROR: define SSHPASS antes de ejecutar este script."
  exit 1
fi

export SSHPASS
SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
mkdir -p "$LOGS_DIR"

for SERVICE in "${FACE_SYNC_SERVICE:-robiotec-face-sync}" "${FACE_EMBEDDINGS_SERVICE:-robiotec-face-embeddings}"; do
  LOGFILE="$LOGS_DIR/${SERVICE}.log"
  $SSH_CMD "$HOST" "journalctl -u $SERVICE --no-pager -n $LINES 2>&1" > "$LOGFILE"
  echo "$SERVICE -> $LOGFILE"
done
