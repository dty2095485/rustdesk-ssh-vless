# Changelog

All notable changes to this fork are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project keeps
one section per published build.

Version numbers are the upstream version plus a fork revision (`1.5.1.2` means
upstream RustDesk `1.5.1`, fork revision `2`), so they are deliberately not
semantic versions. Upstream tags (`1.5.0`, `1.5.1`) live in the source mirror,
fork releases are tagged `v<version>` in this repository.

## [Unreleased]

## [1.5.1.3] - 2026-10-30

Windows-only build: the installer is now packaged exactly like upstream.

### Changed

- libs/portable self-extracting packer replaces the hand-written csc
  bootstrap, so the released EXE carries the RustDesk icon, a version resource
  and the manifest (previously the file showed a blank icon and no version).
- Fork patch: a plain double-click passes `--install` to the payload, keeping
  the previous install-the-service behaviour instead of only running the client.
- Build pipeline fixes required for a clean tag worktree: generate
  `src/ui/inline.rs`, run `flutter pub get` before the bridge codegen, use the
  upstream codegen invocation, keep C debug info (`-Z7`) opt-in because MSVC
  14.44 fails with D8050 on long build paths, and take the packer binary from the
  workspace target directory.

### Notes

- Windows x64 installer only; Android and Docker are unchanged from 1.5.1.2.
- The installer reports the upstream version (1.5.1) in its version resource, as
  the upstream assets do; the fork revision is in the file name and manifest.
## [1.5.1.2] - 2026-10-30

Rebuilt on top of the published 1.5.0.11 source, then merged with upstream
RustDesk 1.5.1.

### Added

- Upstream 1.5.1: configurable keyboard shortcuts, signed update-metadata
  verification, trusted-device V2 with legacy upgrade compatibility, address-book
  button for the web console, Android file transfer through SAF folders.
- Upstream 1.5.1: fixes across DRM/Wayland capture, macOS screen recording,
  Windows installer handoff and service control, WebSocket/WebRTC, clipboard and
  file transfer.

### Changed

- Source baseline is now the published 1.5.0.11 tree (previous 1.5.1.1 build had
  started from a local development tree that predated upstream 1.5.0).

### Fixed

- Windows clipboard file ownership no longer loses the upstream design that
  1.5.0.11 shipped: served file lists, `clipDataId` matching, 16 MiB range split
  and the 1 GiB frame cap are present again, next to the fork's dedicated
  high-throughput clipboard channel. 1.5.1.1 was missing them, which allowed
  another copy during a paste to splice the new file into the transfer and left
  large range requests unbounded.

### Notes

- Windows x64 installer, Android arm64-v8a APK (`versionCode` 12072), Docker
  amd64 archive.
- The Docker archive is the 1.5.1.1 image re-tagged for this version: the server
  binaries are unchanged.

## [1.5.1.1] - 2026-10-30 [superseded]

First merge onto upstream RustDesk 1.5.1 (Windows, Android, Docker).

### Known issues

- Windows clipboard file ownership regressed: the merge started from a stale
  local source tree, so upstream's 1.5.0 clipboard redesign (served file lists,
  `clipDataId`, 16 MiB split) was dropped while the fork's fast channel stayed.
  Superseded by 1.5.1.2; do not use for clipboard file transfers.

## [1.5.0.11] - 2026-10-15

### Fixed

- "No displays" after an RDP session over a RustDesk port forward: the service
  now retries the postponed session switch every 300 ms and performs it as soon
  as no port forward is active.
- Includes the 1.5.0.10 display-list fix.

## [1.5.0.10] - 2026-10-13

### Fixed

- Transient empty display lists during Windows session switches are no longer
  reported as "No Displays": the controlled side holds an empty list for two
  seconds, the controller keeps the current view for five seconds.
- Windows and Android packages in this release.

## [1.5.0.9] - 2026-10-10 [withdrawn]

Guarded internal-panel recovery candidate, withdrawn from testing after a report
of black screen and loss of access during shutdown/reinstallation. The exact
cause was not established. See `releases/1.5.0.9/WITHDRAWN.md` in the release
archive; do not use for unattended upgrades.

## [1.5.0.8] - 2026-10-10

### Fixed

- Pre-authentication recovery: a Windows controller's default desktop connection
  no longer requires authenticated `PeerInfo` before retrying a rendezvous
  failure that followed an observed reset.

## [1.5.0.7] - 2026-10-10

### Fixed

- Connection recovery after a Windows session transition: reset and rendezvous
  failure strings observed in that path are classified as recoverable, so the
  client negotiates again instead of staying offline.

## [1.5.0.6] - 2026-10-10

### Fixed

- The service loop no longer accepts the Windows unavailable-session sentinel in
  its early migration branch (the timed branch already rejected it), closing a
  close-before-invalid-launch path during RDP transitions.

## [1.5.0.2] - 2026-10-04

First package on upstream RustDesk 1.5.0.

### Added

- Windows x64 installer and Android arm64-v8a APK with VLESS TCP+TLS, VLESS
  REALITY, SSH tunnel and JSON network-profile import/export.
- Android configuration import through the system document picker.

### Changed

- Client protocol and platform code moved to `libs/base`; no server address, key
  or SSH credential is built into the packages.

### Fixed

- Android configuration import on API 32 and below after upstream removed
  `READ_EXTERNAL_STORAGE` from the manifest.

## [1.4.9] - 2026-08

Initial fork release on upstream RustDesk 1.4.9 (Windows x86_64), tagged
`v0.1.0` in this repository.

## Intermediate 1.5.0.x test builds

`1.5.0.1` (Android only) and `1.5.0.3` – `1.5.0.5` (Windows only) were
intermediate test builds of the 1.5.0 migration and the RDP session/display
investigation. No separate release notes were kept; per-build artifact records
are in the release archive manifests.
