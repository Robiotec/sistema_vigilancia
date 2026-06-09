#!/usr/bin/env bash
# status.sh
# Muestra estado de los servicios de rostros en 10.0.0.2
# y la galería central en 10.0.0.1.
# Requiere: export SSHPASS=<password_robiotec>
set -euo pipefail

HOST="robiotec@10.0.0.2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"

if [[ -z "${SSHPASS:-}" ]]; then
    echo "AVISO: SSHPASS no definida — omitiendo estado remoto"
    SKIP_REMOTE=1
else
    export SSHPASS
    SKIP_REMOTE=0
fi

SSH_CMD="sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"

if [[ "$SKIP_REMOTE" -eq 0 ]]; then
    echo "=== Servicios en 10.0.0.2 ==="
    $SSH_CMD "$HOST" bash -s <<'REMOTE'
echo "face-sync.timer:       $(systemctl is-active robiotec-face-sync.timer 2>/dev/null)"
echo "face-sync.service:     $(systemctl is-active robiotec-face-sync.service 2>/dev/null)"
echo "face-embed.timer:      $(systemctl is-active robiotec-face-embeddings.timer 2>/dev/null)"
echo "face-embed.service:    $(systemctl is-active robiotec-face-embeddings.service 2>/dev/null)"
echo "Fotos en disco:        $(ls /home/robiotec/Documents/ROSTROS_PERSONAL_SYNC/fotos/ 2>/dev/null | wc -l)"
echo "Index entries:         $(wc -l < /home/robiotec/Documents/ROSTROS_PERSONAL_SYNC/index.jsonl 2>/dev/null || echo 0)"
REMOTE
    echo ""
fi

echo "=== Galería central en 10.0.0.1 ($DATA_DIR) ==="
ls -lh "$DATA_DIR"/*.npz "$DATA_DIR"/*.faiss "$DATA_DIR"/*.json "$DATA_DIR/version" 2>/dev/null || echo "  (sin datos)"

if [[ -f "$DATA_DIR/version" ]]; then
    VER=$(cat "$DATA_DIR/version")
    VER_DATE=$(python3 -c "import datetime; print(datetime.datetime.fromtimestamp(float('$VER')).strftime('%Y-%m-%d %H:%M:%S'))" 2>/dev/null || echo "$VER")
    echo "  Versión galería: $VER_DATE"
fi

if [[ -f "$DATA_DIR/metadata.json" ]]; then
    COUNT=$(python3 -c "import json; print(len(json.load(open('$DATA_DIR/metadata.json'))))" 2>/dev/null || echo "?")
    echo "  Personas en galería: $COUNT"
fi
