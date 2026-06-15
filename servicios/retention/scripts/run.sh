#!/usr/bin/env sh
set -eu

ROOT_DIR="/root/robiotec"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/apicentral/.venv/bin/python}"

exec "$PYTHON_BIN" "$ROOT_DIR/servicios/retention/scripts/cleanup.py" "$@"
