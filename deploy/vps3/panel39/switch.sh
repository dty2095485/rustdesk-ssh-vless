#!/bin/sh
set -eu
umask 077
base=/opt/rustdesk-build/panel39
test "$(docker image inspect rustdesk-server-combined:panel-3.9.0-candidate --format '{{.Id}}')" = sha256:2b643579b7bddc28518a675f0a2bcdb64c8436bb8a6704daa6ccf2ec456c4f7f
test "$(docker inspect rustdesk-server --format '{{.Image}}')" = sha256:385a969a2ae064169453d115dc6b1ae157ab419e9f545fb46170c4586508b721
mkdir -p /opt/rustdesk-backups
backup=$(mktemp -d /opt/rustdesk-backups/panel39-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX)
docker image save -o "$backup/old-image.tar" rustdesk-server-combined:reality-20260929
sha256sum "$backup/old-image.tar" > "$backup/old-image.sha256"
docker inspect rustdesk-server > "$backup/old-container.json"
echo "BACKUP_DIRECTORY=$backup"
docker stop -t 30 rustdesk-server
if ! cp -a /opt/rustdesk-server "$backup/root"; then
    docker start rustdesk-server
    exit 1
fi
rollback_on_failure() {
    code=$?
    if [ "$code" -ne 0 ]; then
        echo 'Cutover check failed; restoring old image AND database' >&2
        sh "$base/rollback.sh" "$backup"
    fi
}
trap rollback_on_failure EXIT
python3 "$base/verify-state.py" "$backup/root" --backup-check
cp "$base/compose-production.yml" /opt/rustdesk-server/compose.yml
docker compose --project-directory /opt/rustdesk-server -f /opt/rustdesk-server/compose.yml up -d --no-build --pull never
healthy=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if [ "$(docker inspect rustdesk-server --format '{{.State.Health.Status}}')" = healthy ]; then healthy=1; break; fi
    sleep 2
done
test "$healthy" = 1
python3 "$base/verify-state.py" "$backup/root"
echo "CUTOVER_HEALTHY; BACKUP_DIRECTORY=$backup"
trap - EXIT
