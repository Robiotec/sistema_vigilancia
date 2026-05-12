#!/usr/bin/env sh
set -eu

tail -n "${LINES:-200}" -f /root/robiotec/servicios/mediamtx/logs/mediamtx.log
