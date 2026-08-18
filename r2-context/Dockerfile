FROM rustdesk/rustdesk-server-s6:1.1.17-vless-combined-r1

COPY hbssh /usr/bin/hbssh
COPY s6-hbssh /etc/s6-overlay/s6-rc.d/hbssh
COPY healthcheck-ssh.sh /usr/bin/healthcheck-ssh.sh

RUN touch /etc/s6-overlay/s6-rc.d/user/contents.d/hbssh \
    && chmod 0755 /usr/bin/hbssh /etc/s6-overlay/s6-rc.d/hbssh/run /usr/bin/healthcheck-ssh.sh

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/usr/bin/healthcheck-ssh.sh"]
