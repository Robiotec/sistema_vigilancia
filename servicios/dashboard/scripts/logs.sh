#!/usr/bin/env sh
set -eu

tail -n "${LINES:-200}" -f /root/robiotec/servicios/dashboard/logs/dashboard.log
