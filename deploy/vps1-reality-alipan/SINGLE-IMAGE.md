# VPS1 single complete image

Completed on the client date 2026-10-03. VPS1 uses a different timezone for the backup directory timestamp.

- Production container: `rustdesk-server`, healthy.
- Sole Docker image: `rustdesk-server-combined:complete-20261003`.
- Image ID prefix: `9b8ff0c6c43a`; size approximately 405 MB.
- The live patched Xray core is included, SHA256 `99c01b48cdb210ea9c264d92932e4d8e980656b591b2354d040ac7060619f73b`.
- Original environment, routes, mount sources, entrypoint and healthcheck were preserved.
- Container-only RustDesk configuration is now persisted in the deployment's `runtime-config` directory, mounted at `/root/.config/rustdesk`.

## Private backup on VPS1

`/var/backups/rustdesk-single-image/20261004-131155-448e40d8`

This directory includes the original image archive, the complete replacement image archive (`complete-image.tar`), original Compose and environment files, container inspection, consistent stopped mounted-data backup, patched core, runtime configuration, checksums and final state. Treat it as private: mounted-data archives and environment files include credentials. Do not publish these backups.

The original image and its 16 intermediate image records were removed only after the replacement passed verification. No Docker volumes, unrelated build caches or host website configurations were deleted. Original image records are recoverable from `original-image.tar`; a rollback must also restore the original Compose/environment and the patched core, not merely load the old image.

## Verified

- Exactly one image record in `docker image ls -a`; loaded image has no parent dependency.
- Production container healthy; patched core hash unchanged.
- Exact generated Xray routing and container environment unchanged.
- REALITY public 443: registration, bidirectional relay, all three UUID users' configured destinations and RustDesk destination restrictions.
- Existing TLS, REALITY, panel, RustDesk and SSH listeners present.
- `example.com`, `nas.example.com` and the private `rd.example.com` panel URL returned HTTP 200 with TLS certificate validation.
- SSH gateway on 2222 returned its protocol banner.

The workflow script is `single_image.py` in this directory and `/opt/rustdesk-tls-fallback/single_image.py` on VPS1. It has phase/state guards; do not rerun preparation blindly after completion. Full interactive remote-control testing was not performed during this image maintenance.
