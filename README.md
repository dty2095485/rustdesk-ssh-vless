# RustDesk SSH+VLESS

A self-hosted [RustDesk](https://github.com/rustdesk/rustdesk) fork that adds two extra
transport modes on top of the stock protocol:

- **SSH tunnel** — client and relay authenticate with a shared built-in ed25519 identity,
  wrapping the RustDesk protocol inside an SSH channel.
- **VLESS + TCP + TLS** — routes traffic through a VLESS gateway (`hbssh`) for use behind
  restrictive networks, with a domain/SNI that looks like ordinary HTTPS.

## Layout

| Path | What it is |
|---|---|
| `client/` | RustDesk desktop client (Rust core + Flutter UI), forked from upstream with SSH/VLESS support added |
| `server/` | RustDesk relay/rendezvous server (`hbbs`/`hbbr`), forked from upstream |
| `hbssh-deploy/` | Standalone SSH gateway (`hbssh`) that bridges the SSH tunnel to the relay's internal ports |
| `nas-arm64-context/`, `r2-context/` | Docker build contexts for running the relay + SSH gateway as containers (ARM64 NAS target, and a generic x86_64 target) |
| `installer/` | Windows single-EXE installer bootstrap (C#) used by `build_installer.ps1` |
| `scripts/nas/` | Helper scripts for benchmarking/inspecting/monitoring the NAS-hosted relay |
| `deploy/vps/` | Iteration history of VPS deployment/diagnostic shell scripts used while standing up the relay (kept for reference; not curated into a single "official" script) |

## Build-time configuration

Earlier revisions of this fork had the SSH identity, VLESS UUID, and relay domain hardcoded
directly in source. Those have been replaced with build-time environment variables so the
checked-in source contains only placeholders. Set these before building your own client/server
to point them at your own infrastructure:

**Client / server (Rust, via `cargo build`, e.g. `set VAR=value` or a `.cargo/config.toml`
`[env]` section that you do not commit):**

| Variable | Used for |
|---|---|
| `RD_RENDEZVOUS_SERVER` | Rendezvous/relay domain (client default ID server + relay-server option) |
| `RD_RENDEZVOUS_PUBKEY` | Rendezvous server's public key (`RS_PUB_KEY`) |
| `RD_RELAY_KEY` | Legacy `key` option for direct-connection mode |
| `RD_VLESS_SERVER` | VLESS gateway host / SNI |
| `RD_VLESS_UUID` | VLESS UUID |
| `RD_SSH_USERNAME` | Built-in SSH username (client) |
| `RD_SSH_PUBLIC_KEY` | Built-in SSH public key (client default + server's authorized key) |
| `RD_SSH_PRIVATE_KEY` | Built-in SSH private key (client) |
| `RD_SSH_HOST_PRIVATE_KEY` | SSH gateway host key (server / `hbssh-deploy`) |

**Flutter UI**, via `flutter build ... --dart-define=RD_VLESS_SERVER=... --dart-define=RD_VLESS_UUID=...`

Without these set, the client/server still compile, but ship with empty/placeholder identities —
the SSH gateway will refuse to start (`Invalid built-in SSH host key`) and VLESS will show
example values until you configure it.

## What's intentionally not in this repo

- `target/`, `build/`, `.dart_tool/` and other build caches
- Compiled binaries and Docker image tarballs (`hbbs`, `hbbr`, `hbssh`, `hbvless`, `*.tar`)
- SSH private keys, TLS certificates, and `known_hosts`
- Personal deployment history: real domain/IP, VPS-side config backups, screenshots, and log dumps
  collected while debugging the relay

## Building

1. Client: see `client/README.md` (upstream RustDesk build docs apply) plus the env vars above.
2. Server: `cargo build --release` inside `server/`, plus the env vars above.
3. Windows installer: `build_installer.ps1` (edit the hardcoded local paths at the top for your machine).
