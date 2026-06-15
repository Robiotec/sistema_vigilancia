#!/usr/bin/env bash
set -euo pipefail

HOST="${FACE_SYNC_HOST:-robiotec@10.0.0.2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${FACES_GALLERY_DIR:-$SCRIPT_DIR/../data}"

if [[ -n "${SSHPASS:-}" ]]; then
  export SSHPASS
  SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
  echo "=== Servicios de rostros en $HOST ==="
  $SSH_CMD "$HOST" bash -s <<'REMOTE'
echo "face-sync.timer:       $(systemctl is-active robiotec-face-sync.timer 2>/dev/null || true)"
echo "face-sync.service:     $(systemctl is-active robiotec-face-sync.service 2>/dev/null || true)"
echo "face-embed.timer:      $(systemctl is-active robiotec-face-embeddings.timer 2>/dev/null || true)"
echo "face-embed.service:    $(systemctl is-active robiotec-face-embeddings.service 2>/dev/null || true)"
REMOTE
  echo ""
else
  echo "SSHPASS no definido; se omite estado remoto."
fi

echo "=== Galeria central: $DATA_DIR ==="
ls -lh "$DATA_DIR"/*.npz "$DATA_DIR"/*.faiss "$DATA_DIR"/*.json "$DATA_DIR/version" 2>/dev/null || echo "sin datos generados"

if [[ -f "$DATA_DIR/metadata.json" ]]; then
  python3 - "$DATA_DIR/metadata.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    payload = json.load(fh)
print(f"Personas en metadata: {len(payload) if hasattr(payload, '__len__') else 0}")
PY
fi
