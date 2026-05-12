#!/usr/bin/env sh
set -eu

tail -n "${LINES:-200}" -f /root/robiotec/servicios/log-cleaner/logs/log-cleaner.log
