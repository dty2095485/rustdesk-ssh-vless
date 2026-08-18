# RustDesk SSH+VLESS

English | [简体中文](README.zh-CN.md)

A self-hosted [RustDesk](https://github.com/rustdesk/rustdesk) fork that adds two extra
transport modes on top of the stock protocol:

- **SSH tunnel** — client and relay authenticate with a shared built-in ed25519 identity,
  wrapping the RustDesk protocol inside an SSH channel.
- **VLESS + TCP + TLS** — routes traffic through a VLESS gateway (`hbssh`) for use behind
  restrictive networks, with a domain/SNI that looks like ordinary HTTPS.

The client also adds a combined config import/export (Settings → Network →
"Import/export all config"): a single JSON file for the ID/relay/API/key server settings plus
VLESS and SSH, on top of upstream's clipboard-only ID/relay/API/key export.

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
   The core DLL **must** be built with `cargo build --release --locked --features flutter`
   (`flutter` is not in Cargo.toml's `default` features) — a plain `cargo build --release`
   silently compiles out the whole flutter_rust_bridge FFI layer the UI depends on, producing
   a DLL about 19MB smaller that looks fine but isn't wired up to the app.

   **First, generate the FFI bridge** — `client/src/bridge_generated.rs` and
   `client/flutter/lib/generated_bridge.dart` are gitignored (matching upstream) and not in
   this repo, so a fresh clone won't compile without running codegen first:
   ```
   cargo install flutter_rust_bridge_codegen --version 1.80.1 --features "uuid" --locked
   cd client
   flutter_rust_bridge_codegen --rust-input ./src/flutter_ffi.rs --dart-output ./flutter/lib/generated_bridge.dart --c-output ./flutter/macos/Runner/bridge_generated.h
   ```
   (needs `flutter` on PATH too, for the Dart-formatting step). Skipping this produces
   `error[E0583]: file not found for module 'bridge_generated'`, which then cascades into a pile
   of unrelated-looking `EventToUI: IntoIntoDart<_>` trait errors that have nothing to do with
   the real cause — lost real time to that exact red herring once already.
2. Server: `cargo build --release` inside `server/`, plus the env vars above.
3. Windows self-extracting exe: `build_portable.ps1` (edit the hardcoded local paths at the top
   for your machine). This drives RustDesk's own official packer at `client/libs/portable/`
   (needs Python 3 + `pip install -r requirements.txt` there) — the same tool upstream RustDesk's
   real releases use, producing a native Rust exe. `installer/` + `build_installer.ps1` (a
   hand-rolled C#/`csc.exe` self-extracting stub) are kept for reference but **not recommended**:
   that packaging shape got blocked by Windows Smart App Control on at least one real x64 Windows
   11 machine (confirmed by comparing the working, official-style build against it) — being
   unsigned and using an unusual/uncommon self-extraction structure both hurt it there, and the
   official packer only fixes the second half of that.

   `build_portable.ps1` also downloads and bundles the two Windows drivers upstream ships this
   way (they're prebuilt/signed elsewhere — driver signing needs real certification, not
   something a plain `cargo`/`flutter` build produces): `usbmmidd_v2` (virtual monitor, for
   controlling a headless machine) from `rustdesk-org/rdev`'s releases, and
   `RustDeskPrinterDriver` + `printer_driver_adapter.dll` (remote printing) from
   `rustdesk/hbb_common`'s releases — both checked against a published/pinned SHA256 before
   being unpacked. Diffing a byte-parsed manifest of a real official 1.4.9 download against our
   own build is what surfaced these as the actual explanation for an installer-size gap that
   first looked suspicious — turned out to be fully accounted for, not anything hidden.
4. Combined server+gateway image (`hbbs`+`hbbr`+`hbvless`+`hbssh` in one container):
   `server/docker-combined/Dockerfile` if you have Docker; or
   `server/docker-combined/build-offline-image.sh` to build and push straight to a registry
   with [crane](https://github.com/google/go-containerregistry) and no local Docker daemon.

## Published artifacts

- Windows installer: see [Releases](../../releases) — built with placeholder connection settings
  only (no real server baked in); import your own config after install via
  Settings → Network → "Import/export all config", or rebuild with the env vars above.
- Combined server+gateway image: `ghcr.io/dty2095485/rustdesk-server-combined:latest`
  (also built without any personal config baked in; configure via the container's `RELAY`,
  `VLESS_UUID`, `VLESS_CERT`, `VLESS_KEY`, `SSH_AUTHORIZED_KEYS` env vars / mounts).
  Also attached to [Releases](../../releases) as `rustdesk-server-combined-docker-x86_64.tar` —
  an offline `docker load`-compatible tarball of the same image, for machines without registry
  access: `docker load -i rustdesk-server-combined-docker-x86_64.tar`.
