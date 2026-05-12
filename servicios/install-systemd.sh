#!/usr/bin/env sh
set -eu

SERVICES_DIR="/root/robiotec/servicios"
SYSTEMD_DIR="/etc/systemd/system"

install -m 0644 "$SERVICES_DIR/apicentral/systemd/robiotec-apicentral.service" "$SYSTEMD_DIR/robiotec-apicentral.service"
install -m 0644 "$SERVICES_DIR/dashboard/systemd/robiotec-dashboard.service" "$SYSTEMD_DIR/robiotec-dashboard.service"
install -m 0644 "$SERVICES_DIR/mediamtx/systemd/robiotec-mediamtx.service" "$SYSTEMD_DIR/robiotec-mediamtx.service"
install -m 0644 "$SERVICES_DIR/arcom/systemd/robiotec-arcom-download.service" "$SYSTEMD_DIR/robiotec-arcom-download.service"
install -m 0644 "$SERVICES_DIR/arcom/systemd/robiotec-arcom-download.timer" "$SYSTEMD_DIR/robiotec-arcom-download.timer"
install -m 0644 "$SERVICES_DIR/osint/systemd/robiotec-osint-download.service" "$SYSTEMD_DIR/robiotec-osint-download.service"
install -m 0644 "$SERVICES_DIR/osint/systemd/robiotec-osint-download.timer" "$SYSTEMD_DIR/robiotec-osint-download.timer"
install -m 0644 "$SERVICES_DIR/log-cleaner/systemd/robiotec-log-cleaner.service" "$SYSTEMD_DIR/robiotec-log-cleaner.service"
install -m 0644 "$SERVICES_DIR/log-cleaner/systemd/robiotec-log-cleaner.timer" "$SYSTEMD_DIR/robiotec-log-cleaner.timer"

systemctl daemon-reload
systemctl enable robiotec-apicentral.service
systemctl enable robiotec-dashboard.service
systemctl enable robiotec-mediamtx.service
systemctl enable robiotec-arcom-download.timer
systemctl enable robiotec-osint-download.timer
systemctl enable robiotec-log-cleaner.timer

echo "Servicios instalados. Para arrancar:"
echo "  systemctl start robiotec-apicentral robiotec-dashboard robiotec-mediamtx"
echo "  systemctl start robiotec-arcom-download.timer robiotec-osint-download.timer robiotec-log-cleaner.timer"
