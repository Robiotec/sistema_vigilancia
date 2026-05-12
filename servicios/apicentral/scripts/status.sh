#!/usr/bin/env sh
set -eu

pgrep -af "uvicorn app.main:app --host 0.0.0.0 --port 8003" || {
  echo "API Central no esta corriendo"
  exit 1
}
