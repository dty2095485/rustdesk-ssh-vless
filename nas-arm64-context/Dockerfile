FROM docker.1ms.run/library/alpine:3.21

COPY hbbs hbbr hbvless hbssh /usr/bin/
COPY start-combined.sh /usr/local/bin/start-combined.sh

RUN chmod 0755 /usr/bin/hbbs /usr/bin/hbbr /usr/bin/hbvless /usr/bin/hbssh /usr/local/bin/start-combined.sh

ENV VLESS_ENABLED=0 \
    VLESS_NAT_INTERNAL=127.0.0.1:22115 \
    VLESS_HBBS_INTERNAL=127.0.0.1:22116 \
    VLESS_HBBR_INTERNAL=127.0.0.1:22117 \
    SSH_LISTEN=0.0.0.0:2222 \
    SSH_NAT=127.0.0.1:22115 \
    SSH_HBBS=127.0.0.1:22116 \
    SSH_HBBR=127.0.0.1:22117

EXPOSE 21115/tcp 21116/tcp 21116/udp 21117/tcp 21118/tcp 21119/tcp 2222/tcp 8443/tcp
WORKDIR /data
ENTRYPOINT ["/usr/local/bin/start-combined.sh"]
