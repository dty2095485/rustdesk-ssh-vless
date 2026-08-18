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

FROM alpine:3.21

ARG S6_OVERLAY_VERSION=3.2.0.0
ARG S6_ARCH=x86_64
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${S6_ARCH}.tar.xz /tmp/

RUN apk add --no-cache \
        ca-certificates \
        libgcc \
        libstdc++ \
        libx11 \
        libxcb \
        libsodium \
        sqlite-libs \
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
COPY docker-combined/rootfs /

RUN chmod 0755 \
    /etc/s6-overlay/s6-rc.d/hbbs/run \
    /etc/s6-overlay/s6-rc.d/hbbr/run \
    /etc/s6-overlay/s6-rc.d/hbvless/run \
    /etc/s6-overlay/s6-rc.d/hbssh/run \
    /etc/s6-overlay/s6-rc.d/key-secret/up.real \
    /usr/bin/healthcheck-combined.sh

ENV RELAY="" \
    ENCRYPTED_ONLY=0 \
    VLESS_LISTEN=0.0.0.0:8443 \
    VLESS_NAT=127.0.0.1:22115 \
    VLESS_HBBS=127.0.0.1:22116 \
    VLESS_HBBR=127.0.0.1:22117 \
    VLESS_NAT_INTERNAL=127.0.0.1:22115 \
    VLESS_HBBS_INTERNAL=127.0.0.1:22116 \
    VLESS_HBBR_INTERNAL=127.0.0.1:22117 \
    VLESS_CERT=/run/tls/fullchain.pem \
    VLESS_KEY=/run/tls/privkey.pem \
    SSH_LISTEN=0.0.0.0:22 \
    SSH_NAT=127.0.0.1:22115 \
    SSH_HBBS=127.0.0.1:22116 \
    SSH_HBBR=127.0.0.1:22117

EXPOSE 21115/tcp 21116/tcp 21116/udp 21117/tcp 21118/tcp 21119/tcp 8443/tcp 22/tcp

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/usr/bin/healthcheck-combined.sh"]

WORKDIR /data
VOLUME ["/data"]
ENTRYPOINT ["/init"]
