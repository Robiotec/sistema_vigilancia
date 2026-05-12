#!/usr/bin/env sh
set -eu

pgrep -af "uvicorn app.main:app --host 0.0.0.0 --port 8010" || {
  echo "Dashboard no esta corriendo"
  exit 1
}
