#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 BACKUP_DIR DEPLOY_DIR" >&2
    exit 2
fi

backup_dir=$1
deploy_dir=$2
rustdesk_data=/www/dk_project/dk_app/rustdesk/rustdesk_rrsC/data
xui_data=/root/my-app/data

if [ -e "$backup_dir" ] || [ -e "$deploy_dir" ]; then
    echo "backup or deployment directory already exists" >&2
    exit 3
fi

mkdir -p "$backup_dir" "$deploy_dir/data" "$deploy_dir/x-ui-data" "$deploy_dir/x-ui-acme"

docker inspect rustdesk-combined-r1 >"$backup_dir/rustdesk-combined-r1.inspect.json"
docker inspect sys_service_app >"$backup_dir/sys_service_app.inspect.json"
docker image inspect rustdesk/rustdesk-server-s6:1.1.17-vless-combined-r2-ssh \
    >"$backup_dir/rustdesk-image.inspect.json"
docker image inspect sys_service_app:3.7.0-offline \
    >"$backup_dir/xui-image.inspect.json"

sqlite3 "$rustdesk_data/db_v2.sqlite3" ".backup '$backup_dir/rustdesk-db.sqlite3'"
cp -a "$rustdesk_data"/id_ed25519* "$backup_dir/"
sqlite3 "$xui_data/x-ui.db" ".backup '$backup_dir/x-ui.db'"
cp -a /root/my-app/docker-compose.yml "$backup_dir/xui-docker-compose.yml"
tar -czf "$backup_dir/rustdesk-vless-config.tgz" /etc/rustdesk-vless
tar -czf "$backup_dir/nginx-config.tgz" \
    /www/server/nginx/conf /www/server/panel/vhost/nginx 2>/dev/null || true

# Candidate copies are independent. The live containers continue writing only
# to their original directories until the explicit cutover step.
sqlite3 "$rustdesk_data/db_v2.sqlite3" ".backup '$deploy_dir/data/db_v2.sqlite3'"
cp -a "$rustdesk_data"/id_ed25519* "$deploy_dir/data/"
sqlite3 "$xui_data/x-ui.db" ".backup '$deploy_dir/x-ui-data/x-ui.db'"
if [ -d /root/.acme.sh ]; then
    cp -a /root/.acme.sh/. "$deploy_dir/x-ui-acme/"
fi

chmod -R go-rwx "$backup_dir" "$deploy_dir/x-ui-data" "$deploy_dir/x-ui-acme"
echo "backup_ready=$backup_dir"
echo "candidate_ready=$deploy_dir"
du -sh "$backup_dir" "$deploy_dir"
