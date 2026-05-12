#!/usr/bin/env sh
set -eu
pgrep -af "mediamtx.*mediamtx.yml" || {
  echo "MediaMTX no esta corriendo"
  exit 1
}
