#!/usr/bin/env sh
set -eu

LINES="${LINES:-200}"
tail -n "$LINES" -f /root/robiotec/servicios/retention/logs/retention-cleanup.log
