#!/usr/bin/env sh
set -eu

tail -n "${LINES:-200}" -f /root/robiotec/servicios/apicentral/logs/apicentral.log
