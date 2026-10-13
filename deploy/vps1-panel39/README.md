# VPS1 official 3X-UI / Xray upgrade

Production image: `rustdesk-server-combined:official-3.9.0-20261004`.
Image ID: `sha256:17f7ed1165fb72af6d16f72619f0511319dae90b75177c7e343574e302dee014`.
Panel: official 3X-UI 3.9.0. Core: official, unmodified Xray 26.9.30.
Core SHA256: `96efb28b8b2086275598dc46e73b5dc340da948b4e1ccc4f1719f83f67b793a7`.

The TLS response-header compatibility patch is no longer used. TLS clients
must use the standard client-first handshake present in client 1.5.0.2.
Windows and Android 1.5.0.2 packages are already published on GitHub. Installed
local Windows EXE and DLL hashes match the verified 1.5.0.2 build payload;
no reinstall was performed. Upgrade other older TLS clients manually.

## Validation

- Isolated migration: users, client settings, routes and panel HTTPS retained.
- Actual RustDesk Rust TLS implementation: registration and bidirectional relay
  passed against the candidate and public VPS1 443.
- All three REALITY users: two configured proxy exits return trusted HTTPS 200;
  RustDesk registration, relay and forbidden-destination checks passed.
- Public website HTTP/1.1, HTTP/2 and no-ALPN fallback passed.
- Public panel reverse proxy HTTPS 200; container healthy, zero restarts.
- Wrong UUID and SSH destination isolation passed.
- Original UTC container timezone retained.

The old header-only TLS handshake intentionally fails with official Xray.
The public probe was run with `--xray-only`, not `--legacy-order`.
Full GUI remote-control sessions still require user testing.

First cutover was rolled back by an overly strict mount comparison. Existing
Compose declared two extra read-only mounts for healthcheck/service enablement
that were absent from the old container's mount list. Recreating the deployment
activated those existing declarations. Second cutover verified the effective
configuration and retained the disabled hbvless service. No public mux, website,
UUID, REALITY key or routing rule was edited.

## Backup and rollback

Current stopped-state backup on VPS1:
`/var/backups/rustdesk-panel39/20261004T130150Z-3eed427f`.

Verified local copy:
`<workspace>\backups\vps1\20261004T130150Z-3eed427f.tar.gz`.
SHA256: `81bdef30c185afbe325e2463e08dd134bb7f62fd3e825f0476e879b4edd72046`.

These archives contain private keys and configuration: never publish them.
VPS1 backup remains remotely available for fast rollback.

```sh
python3 /opt/rustdesk-build/panel39/production.py rollback /var/backups/rustdesk-panel39/20261004T130150Z-3eed427f
```

Rollback restores both image selection and database/mounted writable data,
preserving failed data for diagnosis. Old image is retained; do not prune it
before confirming the client upgrade. Initial rollback backup is separately
retained under `/var/backups/rustdesk-panel39/20261004T130008Z-e625b450`.

## Future upgrades

Change the official `XUI_IMAGE` version/digest in this directory's Dockerfile,
build the complete image, test on database copies and deploy with fresh backups.
No Xray source patch is needed for this TLS handshake issue. Do not use panel
in-place updater scripts in the s6 combined container.

Runtime changes are limited to official panel/core replacement and the isolated
glibc launcher for existing RustDesk binaries. hbbs/hbbr/hbvless/hbssh source,
client production source, network profiles and host Nginx configs were not edited.
