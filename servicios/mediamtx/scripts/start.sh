#!/usr/bin/env sh
set -eu
cd /root/robiotec/mediamtx
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
exec ./mediamtx mediamtx.yml
