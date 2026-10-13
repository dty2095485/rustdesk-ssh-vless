# VPS3 3X-UI 3.9.0 compatibility rebuild

Status: production switched after backup; internal checks and public REALITY probes passed.

Deployed image: `rustdesk-server-combined:panel-3.9.0-candidate`

Image ID: `sha256:2b643579b7bddc28518a675f0a2bcdb64c8436bb8a6704daa6ccf2ec456c4f7f`

Official panel base: `ghcr.io/mhsanaei/3x-ui:v3.9.0@sha256:93a7a68e3d0a65be1b02d2bfc1f3ca02d0e800516a403e103cea2d7c7090855d`

Previous production image: `rustdesk-server-combined:reality-20260929`, ID
`sha256:385a969a2ae064169453d115dc6b1ae157ab419e9f545fb46170c4586508b721`.

## Scope

Use the complete official Alpine panel runtime (bash, curl, OpenSSL, panel CLI,
Xray 26.9.30, frontend and translations). Retain the deployed hbbs/hbbr 1.1.17,
hbvless, hbssh binaries and s6 definitions. Rust source was not changed or
recompiled in this runtime-only rebuild. glibc binaries run with an isolated
loader/library directory; they do not replace Alpine's musl or libgcc.

No credentials, database, certificate or connection profile is embedded in the
new image. Keep private test snapshots on the server and never upload them.

## Verification

- Online SQLite backup used for the independent test database.
- Database integrity check passes after migration.
- One inbound and all three clients retain their settings/REALITY parameters.
- Panel responds HTTP 200 at the existing URI path.
- All five s6 services and existing health-check listeners pass.
- Xray configuration validation passes.
- Existing RustDesk REALITY credential reaches NAT/registration services.
- hbbr transmits 66,000 test bytes in both directions over REALITY.
- RustDesk credential cannot proxy SSH port 22.
- Existing proxy credential reaches Internet HTTPS with a trusted certificate.
- Proxy credential cannot access the private RustDesk backend.

The second proxy credential was preserved but not separately exercised.
After cutover, public 443 REALITY registration, bidirectional relay and proxy
Internet HTTPS probes passed. Backend ports 21115-21119, 2053 and 2222 remain
unreachable publicly. An actual desktop-control session still needs user testing.

## Production backup and rollback

Stopped-state backup has been moved to the verified local archive:
`<workspace>\backups\vps3\panel39-20261004T123658Z-bySBXD.tar.gz`.
SHA256: `91f07281058ac3c2d52243b9e6aa5caf939f56d361066a1182943a9ff5a2048f`.
The corresponding remote directory and temporary archive were deleted only after
archive and embedded old-image checksum verification.

Includes the old image archive/checksum, container metadata and the complete
pre-migration deployment directory (databases, configuration and keys). Private:
do not publish or upload to GitHub.

To roll back, first upload the local archive and extract it under
`/opt/rustdesk-backups`, then run on VPS3:

```sh
sh /opt/rustdesk-build/panel39/rollback.sh /opt/rustdesk-backups/panel39-20261004T123658Z-bySBXD
```

This stops the new container, preserves its migrated files, restores the old
deployment directory, and recreates the old-image container. Verify health
and public connection probes afterward.

## Upgrade policy

Rebuild/replace the complete image for future panel upgrades. The built-in
panel updater is not validated for this combined s6 environment; merely adding
bash does not make systemd/OpenRC installation scripts compatible with s6.

Before any production cutover, take a fresh database/config backup and retain
the old image. If rolling back a database migration, restore the pre-upgrade
database together with the old image. Do not run `down -v` or delete volumes.

Local build files are here; server build context is `/opt/rustdesk-build/panel39`.
Production compose remains `/opt/rustdesk-server/compose.yml`.
