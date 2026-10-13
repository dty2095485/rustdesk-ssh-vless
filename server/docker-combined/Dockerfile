# syntax=docker/dockerfile:1.7

FROM rust:1.88-alpine3.21 AS builder

RUN apk add --no-cache \
    autoconf \
    automake \
    build-base \
    cmake \
    git \
    libtool \
    libx11-dev \
    libsodium-dev \
    linux-headers \
    openssl-dev \
    openssl-libs-static \
    perl \
    pkgconf \
    sqlite-dev

WORKDIR /src
COPY Cargo.toml Cargo.lock build.rs ./
COPY src ./src
COPY libs/hbb_common ./libs/hbb_common
RUN cargo build --release --locked \
    --bin hbbs \
    --bin hbbr \
    --bin hbvless \
    --bin hbssh \
    --bin rustdesk-utils

# Pin the official 3x-ui image and copy its multi-arch panel/Xray payload into
# the final supervised RustDesk image. Docker selects the matching amd64/arm64
# image for the target platform automatically.
FROM ghcr.io/mhsanaei/3x-ui:v3.8.5@sha256:e0f90c10902e0e74f947d5a9efe017b273804477430233bbfc4918542ffe366c AS xui

FROM alpine:3.21

ARG S6_OVERLAY_VERSION=3.2.0.0
ARG S6_ARCH=x86_64
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz /tmp/

RUN apk add --no-cache \
        ca-certificates \
        bash \
        curl \
        fail2ban \
        libgcc \
        libstdc++ \
        libx11 \
        libxcb \
        libsodium \
        openssl \
        sqlite-libs \
        tzdata \
        xz \
    && tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C / -Jxpf /tmp/s6-overlay-${S6_ARCH}.tar.xz \
    && rm /tmp/s6-overlay-*.tar.xz \
    && if [ ! -e /var/run ]; then ln -s /run /var/run; fi

COPY --from=builder /src/target/release/hbbs /usr/bin/hbbs
COPY --from=builder /src/target/release/hbbr /usr/bin/hbbr
COPY --from=builder /src/target/release/hbvless /usr/bin/hbvless
COPY --from=builder /src/target/release/hbssh /usr/bin/hbssh
COPY --from=builder /src/target/release/rustdesk-utils /usr/bin/rustdesk-utils
COPY --from=xui /app /app
COPY --from=xui /usr/bin/x-ui /usr/bin/x-ui
COPY --from=xui /etc/fail2ban /etc/fail2ban
COPY docker-combined/rootfs /

RUN chmod 0755 \
    /etc/s6-overlay/s6-rc.d/hbbs/run \
    /etc/s6-overlay/s6-rc.d/hbbr/run \
    /etc/s6-overlay/s6-rc.d/hbvless/run \
    /etc/s6-overlay/s6-rc.d/hbssh/run \
    /etc/s6-overlay/s6-rc.d/reality-ui/run \
    /etc/s6-overlay/s6-rc.d/key-secret/up.real \
    /usr/bin/healthcheck-combined.sh \
    /app/DockerEntrypoint.sh \
    /app/x-ui \
    /usr/bin/x-ui

ENV RELAY="" \
    ENCRYPTED_ONLY=0 \
    VLESS_LISTEN=127.0.0.1:8443 \
    VLESS_NAT=127.0.0.1:22115 \
    VLESS_HBBS=127.0.0.1:22116 \
    VLESS_HBBR=127.0.0.1:22117 \
    VLESS_NAT_INTERNAL=127.0.0.1:22115 \
    VLESS_HBBS_INTERNAL=127.0.0.1:22116 \
    VLESS_HBBR_INTERNAL=127.0.0.1:22117 \
    VLESS_CERT=/run/tls/fullchain.pem \
    VLESS_KEY=/run/tls/privkey.pem \
    SSH_LISTEN=0.0.0.0:2222 \
    SSH_NAT=127.0.0.1:22115 \
    SSH_HBBS=127.0.0.1:22116 \
    SSH_HBBR=127.0.0.1:22117 \
    XUI_IN_DOCKER=true \
    XUI_MAIN_FOLDER=/app \
    XUI_PORT=2053 \
    XRAY_VMESS_AEAD_FORCED=false \
    XUI_ENABLE_FAIL2BAN=false \
    XUI_DB_TYPE= \
    XUI_DB_DSN=

EXPOSE 21115/tcp 21116/tcp 21116/udp 21117/tcp 21118/tcp 21119/tcp 8443/tcp 10443/tcp 2053/tcp 2222/tcp

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/usr/bin/healthcheck-combined.sh"]

WORKDIR /data
VOLUME ["/data", "/etc/x-ui", "/root/.acme.sh"]
ENTRYPOINT ["/init"]
