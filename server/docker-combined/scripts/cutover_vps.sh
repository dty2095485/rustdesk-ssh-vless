#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 DEPLOY_ROOT FINAL_BACKUP_DIR" >&2
    exit 2
fi

deploy_root=$1
final_backup=$2
compose_file=$deploy_root/docker-combined/docker-compose.yml
env_file=$deploy_root/docker-combined/.env
candidate_data=$deploy_root/docker-combined/data
live_data=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC/data
old_rustdesk=rustdesk-combined-r1
old_xui=sys_service_app
new_container=rustdesk-server

rollback() {
    status=$?
    trap - EXIT INT TERM
    echo "cutover_failed_status=$status; rolling back" >&2
    docker compose --env-file "$env_file" -f "$compose_file" stop rustdesk-server \
        >/dev/null 2>&1 || true
    docker rm -f "$new_container" >/dev/null 2>&1 || true
    docker start "$old_rustdesk" "$old_xui" >/dev/null 2>&1 || true
    echo "rollback_old_containers_started" >&2
    exit "$status"
}
trap rollback EXIT INT TERM

test -f "$compose_file"
test -f "$env_file"
nginx -t

docker rm -f rustdesk-server-preflight-20260929 >/dev/null 2>&1 || true
mkdir -p "$final_backup"
sqlite3 "$live_data/db_v2.sqlite3" ".backup '$final_backup/rustdesk-db.sqlite3'"
sqlite3 /root/my-app/data/x-ui.db ".backup '$final_backup/x-ui.db'"
docker inspect "$old_rustdesk" >"$final_backup/rustdesk.inspect.json"
docker inspect "$old_xui" >"$final_backup/xui.inspect.json"

docker stop -t 30 "$old_rustdesk" "$old_xui" >/dev/null

# Refresh the registration database only after the old hbbs is stopped. The
# candidate x-ui database stays on the already-tested 3.8 schema with the new
# isolated Reality user and copied legacy proxy users.
rm -f "$candidate_data/db_v2.sqlite3-wal" "$candidate_data/db_v2.sqlite3-shm"
sqlite3 "$live_data/db_v2.sqlite3" ".backup '$candidate_data/db_v2.sqlite3'"
cp -a "$live_data"/id_ed25519* "$candidate_data/"

docker compose --env-file "$env_file" -f "$compose_file" up -d --no-build rustdesk-server

i=0
while [ "$i" -lt 18 ]; do
    health=$(docker inspect "$new_container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || true)
    [ "$health" = healthy ] && break
    i=$((i + 1))
    sleep 5
done
test "${health:-}" = healthy

for port in 21115 21116 21117 21118 21119 2222; do
    ss -lnt | awk -v suffix=":$port" '$4 ~ (suffix "$") { found=1 } END { exit found ? 0 : 1 }'
done
for port in 8443 10443 2053 22115 22116 22117; do
    ss -lnt | awk -v endpoint="127.0.0.1:$port" '$4 == endpoint { found=1 } END { exit found ? 0 : 1 }'
done
ss -lnu | awk '$4 ~ /:21116$/ { found=1 } END { exit found ? 0 : 1 }'

curl --noproxy '*' -kfsS --resolve example.com:443:127.0.0.1 \
    https://example.com/ >/dev/null

trap - EXIT INT TERM
echo "cutover_success container=$new_container health=$health"
docker ps --filter "name=^/$new_container$" --format '{{.Names}} {{.Image}} {{.Status}}'
