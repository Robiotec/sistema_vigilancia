#!/usr/bin/env sh
set -eu

systemctl status robiotec-retention-cleanup.timer --no-pager
systemctl list-timers robiotec-retention-cleanup.timer --no-pager
