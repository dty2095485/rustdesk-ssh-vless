#!/bin/sh
set -eu
backup=$(realpath "$1")
case "$backup" in /opt/rustdesk-backups/panel39-*) ;; *) echo 'Invalid backup directory' >&2; exit 1;; esac
test -f "$backup/root/compose.yml"
test -f "$backup/root/x-ui-data/x-ui.db"
test ! -e "$backup/failed-production"
docker stop -t 30 rustdesk-server || true
# Preserve migrated data for diagnosis; never delete it or restore just the image.
mv /opt/rustdesk-server "$backup/failed-production"
cp -a "$backup/root" /opt/rustdesk-server
docker compose --project-directory /opt/rustdesk-server -f /opt/rustdesk-server/compose.yml up -d --no-build --pull never
echo "ROLLED_BACK: $backup"
