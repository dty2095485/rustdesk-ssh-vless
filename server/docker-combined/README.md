# RustDesk single-container VLESS stack

One Compose project builds and starts one supervised `rustdesk-server`
container containing:

- `hbbs` and `hbbr` (official RustDesk traffic)
- `hbvless` (existing VLESS TCP+TLS gateway)
- `hbssh` (existing SSH gateway)
- 3x-ui and its bundled Xray Core (VLESS TCP+REALITY plus Web UI)

TLS, SSH and official RustDesk behavior is unchanged. REALITY is an additional
mode and has its own UUID/public key/short ID. The Windows client can select
Off, TLS or REALITY; Off continues to use the official RustDesk ports.

## Ports and isolation

- TCP 21115-21119 and UDP 21116: official RustDesk listeners.
- `127.0.0.1:8443`: existing `hbvless` TLS listener, reached through the host
  SNI/ALPN stream proxy.
- `127.0.0.1:10443`: Xray REALITY inbound, also reached through the host stream
  proxy.
- `127.0.0.1:2053`: 3x-ui panel. It is not public by default.
- `${SSH_HOST_PORT:-2222}`: existing SSH gateway.
- TCP 22115-22117: authenticated-only RustDesk endpoints. They bind only to
  loopback inside the container and are not published by Compose.

The container uses Linux host networking. This is intentional: Xray can reach
the existing host-only website listener at `127.0.0.1:4443`, while the
authenticated RustDesk listeners remain loopback-only. Compose explicitly
binds hbvless to `127.0.0.1:8443`, forces the Web UI to
`127.0.0.1:2053`, and starts hbssh on `${SSH_HOST_PORT:-2222}` so it does not
collide with the VPS SSH daemon on port 22.

## One-time setup

Copy `.env.example` to the untracked `.env` file and fill in:

- `RELAY`
- `VLESS_UUID` for the existing TCP+TLS mode
- the absolute certificate/key paths
- the existing SSH settings if used

The image forces the panel to loopback when it starts. Open it safely with an
SSH tunnel:

```sh
ssh -L 2053:127.0.0.1:2053 root@your-vps
```

Then browse to `http://127.0.0.1:2053`. The upstream default login is
`admin` / `admin`; change it immediately and enable two-factor authentication.
The existing panel/subscription certificate directory is mounted read-only at
`/root/cert` through `XUI_CERT_DIR`, so migrated 3x-ui paths remain valid.

## REALITY Web UI parameters

Create a VLESS inbound in 3x-ui:

```text
Remark: rustdesk-reality
Listen IP: 127.0.0.1
Port: 10443
Protocol: VLESS
Transport: RAW/TCP
Security: REALITY
Target: 127.0.0.1:4443
Server name: rd.example.com
Flow: xtls-rprx-vision
Fallbacks: empty
```

Create a client UUID and generate a REALITY key pair plus a non-empty short
ID. Copy the UUID, public key, short ID and SNI to the client's REALITY page.
The private key stays only in `/etc/x-ui`.

For defense in depth, add Xray routing rules scoped to this inbound:

1. Send only IP `127.0.0.1`, ports `22115-22117`, to the normal direct
   outbound.
2. Send all remaining traffic from the same inbound to a blackhole outbound.

The shipped client already rewrites RustDesk's 21115-21117 requests to those
three authenticated-only ports. The server routing rule prevents a leaked
REALITY UUID from becoming a general-purpose proxy.

The host stream map in `host-nginx/vless_mux.conf` keeps the public layout:

```text
public :443
├─ nas.example.com + browser ALPN -> 127.0.0.1:4443 website
├─ nas.example.com + VLESS TLS    -> 127.0.0.1:8443
├─ rd.example.com                 -> 127.0.0.1:10443 REALITY
└─ example.com/default            -> 127.0.0.1:4443 website
```

## Build and start with one command

For the amd64 VPS, `Dockerfile.runtime` packages the five release binaries
compiled in WSL from `/home/dty/build-ssh-r2`. This avoids compiling Rust on
the low-memory production VPS. `Dockerfile` remains the portable full-source
build; select it with `DOCKERFILE=docker-combined/Dockerfile` (and
`S6_ARCH=aarch64` on the ARM NAS).

Run from the repository root:

```sh
docker compose --env-file docker-combined/.env \
  -f docker-combined/docker-compose.yml up -d --build
```

Check all supervised processes and listeners:

```sh
docker compose --env-file docker-combined/.env \
  -f docker-combined/docker-compose.yml ps
docker logs --tail 200 rustdesk-server-canary
```

The container is healthy only when hbbs, hbbr, hbvless, hbssh, 3x-ui/Xray
management are up. Port 10443 is created after the REALITY inbound is saved
and enabled in the Web UI.

After renewing the TCP+TLS certificate, restart only hbvless:

```sh
docker exec rustdesk-server-canary \
  /package/admin/s6/command/s6-svc -r /run/s6-rc/servicedirs/hbvless
```

## Canary and rollback

Do not let two hbbs processes write the same SQLite data directory. For a
canary, first copy the existing data into `docker-combined/data`, keep the old
containers/images/volumes intact, stop the old stack, and then start this one.
Test official mode, TLS mode, REALITY mode, SSH mode, iOS access, fixed and
one-time passwords, relay sessions, file transfer, and website fallback before
making it production.

Rollback is non-destructive:

```sh
docker compose --env-file docker-combined/.env \
  -f docker-combined/docker-compose.yml stop rustdesk-server
cd /path/to/original-deployment
docker compose up -d
```

Never use `down -v` during rollback. Retain `data`, `x-ui-data`, and
`x-ui-acme` until recovery is verified.
