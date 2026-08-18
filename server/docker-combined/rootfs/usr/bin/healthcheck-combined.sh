#!/bin/sh
set -eu

S6_SVSTAT=/package/admin/s6/command/s6-svstat

check_service() {
    status="$($S6_SVSTAT "/run/s6-rc/servicedirs/$1")" || return 1
    case "$status" in
        up*) return 0 ;;
        *) echo "s6 service is not up: $1 ($status)" >&2; return 1 ;;
    esac
}

check_tcp_listener() {
    netstat -lnt | awk -v suffix=":$1" '
        $4 ~ (suffix "$") && $6 == "LISTEN" { found = 1 }
        END { exit found ? 0 : 1 }
    ' || {
        echo "TCP listener is missing: $1" >&2
        return 1
    }
}

check_udp_listener() {
    netstat -lnu | awk -v suffix=":$1" '
        $4 ~ (suffix "$") { found = 1 }
        END { exit found ? 0 : 1 }
    ' || {
        echo "UDP listener is missing: $1" >&2
        return 1
    }
}

for service in hbbs hbbr hbvless hbssh; do
    check_service "$service"
done

for port in 21115 21116 21117 21118 21119 8443 22 22115 22116 22117; do
    check_tcp_listener "$port"
done
check_udp_listener 21116

