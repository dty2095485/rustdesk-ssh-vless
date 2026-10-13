# VPS1 amd64: retain proven RustDesk binaries/s6 definitions, use the complete
# official panel runtime. No database, connection profile or private key is copied.
ARG LEGACY_IMAGE=rustdesk-server-combined:complete-20261003
ARG XUI_IMAGE=ghcr.io/mhsanaei/3x-ui:v3.9.0@sha256:93a7a68e3d0a65be1b02d2bfc1f3ca02d0e800516a403e103cea2d7c7090855d
FROM ${LEGACY_IMAGE} AS legacy
FROM ${XUI_IMAGE}

COPY --from=legacy /package /package
COPY --from=legacy /command /command
COPY --from=legacy /init /init
COPY --from=legacy /etc/s6-overlay /etc/s6-overlay
COPY --from=legacy /usr/bin/hbbs /usr/bin/hbbr /usr/bin/hbvless /usr/bin/hbssh /usr/bin/rustdesk-utils /opt/rustdesk/bin/
# Keep glibc and musl separate. In particular, do not replace Alpine's libgcc.
COPY --from=legacy /lib/ld-linux-x86-64.so.2 /lib/libc.so.6 /lib/libm.so.6 /lib/libgcc_s.so.1 /lib/libpthread.so.0 /lib/libresolv.so.2 /lib/libnss_dns.so.2 /lib/libnss_files.so.2 /opt/rustdesk/glibc/
COPY --from=legacy /usr/bin/healthcheck-combined.sh /usr/bin/healthcheck-combined.sh
RUN set -eu; \
    for name in hbbs hbbr hbvless hbssh rustdesk-utils; do \
        printf '#!/bin/sh\nexec /opt/rustdesk/glibc/ld-linux-x86-64.so.2 --library-path /opt/rustdesk/glibc /opt/rustdesk/bin/%s "$@"\n' "$name" > "/usr/bin/$name"; \
        chmod 0755 "/usr/bin/$name"; \
    done; \
    /bin/bash --version >/dev/null; curl --version >/dev/null; \
    test -x /usr/bin/x-ui; test -x /app/x-ui; \
    /usr/bin/hbbs --version; /usr/bin/hbbr --version

ENV TZ=UTC RELAY="" ENCRYPTED_ONLY=0 \
    VLESS_LISTEN=127.0.0.1:8443 \
    VLESS_NAT=127.0.0.1:22115 VLESS_HBBS=127.0.0.1:22116 VLESS_HBBR=127.0.0.1:22117 \
    VLESS_NAT_INTERNAL=127.0.0.1:22115 VLESS_HBBS_INTERNAL=127.0.0.1:22116 VLESS_HBBR_INTERNAL=127.0.0.1:22117 \
    VLESS_CERT=/run/tls/fullchain.pem VLESS_KEY=/run/tls/privkey.pem \
    SSH_LISTEN=127.0.0.1:2222 SSH_NAT=127.0.0.1:22115 SSH_HBBS=127.0.0.1:22116 SSH_HBBR=127.0.0.1:22117 \
    XUI_IN_DOCKER=true XUI_MAIN_FOLDER=/app XUI_PORT=2053 XUI_ENABLE_FAIL2BAN=false
LABEL org.opencontainers.image.title="RustDesk combined with official 3X-UI" \
    org.opencontainers.image.version="3x-ui-3.9.0" \
    org.opencontainers.image.description="VPS1 official panel and unpatched Xray; upgrade by replacing image"
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 CMD ["/usr/bin/healthcheck-combined.sh"]
WORKDIR /data
VOLUME ["/data", "/etc/x-ui", "/root/.acme.sh"]
ENTRYPOINT ["/init"]
CMD []
