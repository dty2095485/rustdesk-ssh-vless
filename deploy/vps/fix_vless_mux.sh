#!/usr/bin/env bash
# Idempotent VLESS SNI mux repair. Safe to run any time (cron/manual/systemd).
NGINX_BIN=/www/server/nginx/sbin/nginx
VHOST_DIR=/www/server/panel/vhost/nginx
CONF="$VHOST_DIR/your-domain.example.conf"
PIDFILE=/www/server/nginx/logs/nginx.pid
LOG=/var/log/vless-mux-fix.log
CHANGED=0
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# Self-heal an empty nginx pid file (breaks `nginx -s` and BT panel reloads).
MASTER=$(pgrep -x nginx | head -1)
if [ -f "$PIDFILE" ] && [ ! -s "$PIDFILE" ] && [ -n "$MASTER" ]; then
  echo "$MASTER" > "$PIDFILE"
  log "repaired empty nginx pid file (master $MASTER)"
fi

[ -f "$CONF" ] || { log "site conf missing, nothing to do"; exit 0; }

fix_listen() {
  # Move the panel's `listen 443 ssl;` to the loopback backend port.
  local tmp; tmp=$(mktemp)
  sed 's/^\(\s*\)listen 443 ssl;$/\1listen 127.0.0.1:4443 ssl;/' "$CONF" > "$tmp"
  if ! cmp -s "$tmp" "$CONF"; then
    cat "$tmp" > "$CONF"
    CHANGED=1
  fi
  rm -f "$tmp"
}

fix_redirect() {
  # $server_port is 4443 behind the mux; only redirect plain port-80 hits.
  if grep -q 'if (\$server_port != 443) {' "$CONF"; then
    local tmp; tmp=$(mktemp)
    sed 's/if (\$server_port != 443) {/if (\$server_port = 80) {/' "$CONF" > "$tmp"
    cat "$tmp" > "$CONF"
    CHANGED=1
    rm -f "$tmp"
  fi
}

fix_mux_file() {
  if [ ! -f "$VHOST_DIR/tcp/vless_mux.conf" ]; then
    cat > "$VHOST_DIR/tcp/vless_mux.conf" <<'EOF'
map $ssl_preread_server_name $rd_sni {
    nas.your-domain.example 127.0.0.1:8443;
    default        127.0.0.1:4443;
}
map $ssl_preread_protocol $rd_backend {
    ""              172.18.0.50:21117;
    default         $rd_sni;
}
server {
    listen 443;
    proxy_pass $rd_backend;
    ssl_preread on;
    proxy_connect_timeout 5s;
    proxy_timeout 24h;
}
EOF
    CHANGED=1
  fi
}

fix_listen
fix_redirect
fix_mux_file

if [ "$CHANGED" = 1 ]; then
  if "$NGINX_BIN" -t 2>>"$LOG"; then
    if pgrep -x nginx >/dev/null; then
      # Running nginx keeps its healthy config even when the panel's own
      # reload failed; a plain reload is enough once the file is repaired.
      if "$NGINX_BIN" -s reload 2>>"$LOG"; then
        log "applied fix and reloaded nginx"
      elif MASTER=$(pgrep -x nginx | head -1) && [ -n "$MASTER" ] && kill -HUP "$MASTER" 2>/dev/null; then
        log "-s reload failed, sent HUP to master $MASTER"
      else
        log "reload failed, nginx kept previous config (still healthy)"
      fi
    fi
  else
    log "nginx -t failed after fix; left config as-is"
    exit 1
  fi
else
  log "checked, no fix needed"
fi

# Safety net: the panel may restart nginx around the same time, racing with
# this repair. If nginx ends up down, start it (the config is valid now).
start_if_down() {
  if ! pgrep -x nginx >/dev/null; then
    "$NGINX_BIN" 2>>"$LOG" && log "nginx was down, started it"
  fi
}
start_if_down
for i in 1 2 3 4 5 6; do
  sleep 3
  start_if_down
done
