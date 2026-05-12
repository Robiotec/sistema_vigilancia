#!/usr/bin/env sh
set -eu

systemctl list-timers robiotec-log-cleaner.timer --no-pager
