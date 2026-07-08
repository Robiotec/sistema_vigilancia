#!/usr/bin/env sh
set -eu

SERVICES_DIR="/root/robiotec/servicios"
PLATFORM_DIR="/root/robiotec/plataforma"
SYSTEMD_DIR="/etc/systemd/system"

install -m 0644 "$PLATFORM_DIR/systemd/robiotec-django.service" "$SYSTEMD_DIR/robiotec-django.service"
install -m 0644 "$PLATFORM_DIR/systemd/robiotec-celery.service" "$SYSTEMD_DIR/robiotec-celery.service"
install -m 0644 "$PLATFORM_DIR/systemd/robiotec-celerybeat.service" "$SYSTEMD_DIR/robiotec-celerybeat.service"
install -m 0644 "$SERVICES_DIR/apicentral/systemd/robiotec-apicentral.service" "$SYSTEMD_DIR/robiotec-apicentral.service"
install -m 0644 "$SERVICES_DIR/mediamtx/systemd/robiotec-mediamtx.service" "$SYSTEMD_DIR/robiotec-mediamtx.service"
install -m 0644 "$SERVICES_DIR/arcom/systemd/robiotec-arcom-download.service" "$SYSTEMD_DIR/robiotec-arcom-download.service"
install -m 0644 "$SERVICES_DIR/arcom/systemd/robiotec-arcom-download.timer" "$SYSTEMD_DIR/robiotec-arcom-download.timer"
install -m 0644 "$SERVICES_DIR/osint/systemd/robiotec-osint-download.service" "$SYSTEMD_DIR/robiotec-osint-download.service"
install -m 0644 "$SERVICES_DIR/osint/systemd/robiotec-osint-download.timer" "$SYSTEMD_DIR/robiotec-osint-download.timer"
install -m 0644 "$SERVICES_DIR/log-cleaner/systemd/robiotec-log-cleaner.service" "$SYSTEMD_DIR/robiotec-log-cleaner.service"
install -m 0644 "$SERVICES_DIR/log-cleaner/systemd/robiotec-log-cleaner.timer" "$SYSTEMD_DIR/robiotec-log-cleaner.timer"
install -m 0644 "$SERVICES_DIR/retention/systemd/robiotec-retention-cleanup.service" "$SYSTEMD_DIR/robiotec-retention-cleanup.service"
install -m 0644 "$SERVICES_DIR/retention/systemd/robiotec-retention-cleanup.timer" "$SYSTEMD_DIR/robiotec-retention-cleanup.timer"

systemctl daemon-reload
systemctl enable robiotec-apicentral.service
systemctl enable robiotec-django.service
systemctl enable robiotec-celery.service
systemctl enable robiotec-celerybeat.service
systemctl enable robiotec-mediamtx.service
systemctl enable robiotec-arcom-download.timer
systemctl enable robiotec-osint-download.timer
systemctl enable robiotec-log-cleaner.timer
systemctl enable robiotec-retention-cleanup.timer

echo "Servicios instalados. Para arrancar:"
echo "  systemctl start robiotec-django robiotec-celery robiotec-celerybeat robiotec-apicentral robiotec-mediamtx"
echo "  systemctl start robiotec-arcom-download.timer robiotec-osint-download.timer robiotec-log-cleaner.timer robiotec-retention-cleanup.timer"
