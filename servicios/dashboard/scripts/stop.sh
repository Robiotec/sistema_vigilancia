#!/usr/bin/env sh
set -eu

pkill -f "uvicorn app.main:app --host 0.0.0.0 --port 8010" || true
