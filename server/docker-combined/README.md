# RustDesk combined canary container

This experimental image supervises `hbbs`, `hbbr`, `hbvless`, and `hbssh` as
four independent s6 services. It does not reuse or overwrite the existing
`docker/` image assets.

## Traffic boundaries

- Official public listeners remain on TCP 21115-21119 and UDP 21116.
- `hbvless` listens on container port 8443. Compose publishes it only as
  `127.0.0.1:8443`, for a host-side TLS/SNI stream proxy.
- The authenticated internal listeners are loopback-only:
  `127.0.0.1:22115` (NAT), `127.0.0.1:22116` (hbbs), and
  `127.0.0.1:22117` (hbbr). They are never published by Compose.
- A VLESS credential is checked by `hbvless` before traffic reaches an internal
  listener. The internal listeners are explicit protocol entries; they do not
  infer trust from a generic loopback source address.
- `hbssh` listens on container port 22 and authenticates with the built-in
  ed25519 public key (or extra keys from `SSH_AUTHORIZED_KEYS`), then forwards
  `direct-tcpip` channels to the same internal listeners. Compose publishes it
  as `${SSH_HOST_PORT:-22}:22`.

## Build and canary test

1. Copy `.env.example` to `.env`, fill it locally, and restrict its permissions.
   The tracked template contains no UUID or private-key material.
2. Build from the repository root with `sh docker-combined/build-image.sh`, or run
   `docker compose --env-file docker-combined/.env -f docker-combined/docker-compose.yml build`.
3. For a canary, copy the existing `/data` directory to
   `docker-combined/data`. Never let two `hbbs` processes write the same live
   SQLite directory.
4. Keep the existing two containers and images intact. Stop them without
   removing their volumes, then start this stack:

   ```sh
   docker compose --env-file docker-combined/.env -f docker-combined/docker-compose.yml up -d
   docker compose --env-file docker-combined/.env -f docker-combined/docker-compose.yml ps
   ```

5. Confirm the container is healthy, the website still works through its SNI
   route, and test official TCP/UDP, VLESS-on, VLESS-off, SSH-on, SSH-off,
   fixed-password, one-time-password, and a sustained relay session.

The host stream proxy should forward only the VLESS SNI branch to
`127.0.0.1:8443`. Port 8443 does not need a public firewall rule.

After certificate renewal, reload only the gateway service so official sessions
are not restarted:

```sh
docker exec rustdesk-combined-canary \
  /package/admin/s6/command/s6-svc -r /run/s6-rc/servicedirs/hbvless
```

## Rollback

Rollback is deliberately non-destructive:

1. Stop the combined container first. Do not use `down -v`.
2. From the original deployment directory, start the original hbbs/hbbr and
   hbvless containers with their saved Compose file.
3. Confirm official and VLESS registrations before removing the canary.
4. Only after recovery is verified may the stopped canary container and its
   uniquely tagged image be removed. Keep its copied data until no longer
   needed.

Example sequence (replace the old deployment path; do not run both stacks at
the same time):

```sh
docker compose --env-file docker-combined/.env \
  -f docker-combined/docker-compose.yml stop rustdesk-combined
cd /path/to/original-two-container-deployment
docker compose up -d
```
