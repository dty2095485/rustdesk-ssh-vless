# RustDesk VLESS / SSH

[中文说明](README.zh-CN.md)

A fork of the RustDesk 1.5.0 client and RustDesk Server 1.1.17 that can reach the
RustDesk ID/relay server through an SSH tunnel or VLESS (TCP+TLS or REALITY),
with network settings exported to and imported from a JSON file.

Current release: [1.5.0.10](https://github.com/dty2095485/rustdesk-ssh-vless/releases/tag/v1.5.0.10)

## Downloads

Installers are on the [Releases](https://github.com/dty2095485/rustdesk-ssh-vless/releases) page:

- **Windows x64**: single-file installer. It is unsigned and may trigger a security warning.
- **Android ARM64**: APK. REALITY requires Android 7 (API 24) or newer.

No server addresses, keys or SSH credentials are built in. After installing, enter
your own settings or import a network configuration JSON file.

## Repository layout

| Path | Contents |
|---|---|
| `client/` | Windows / Android client: Rust core and Flutter UI, with SSH, VLESS TCP+TLS, REALITY and JSON import/export |
| `server/` | `hbbs`, `hbbr` and the `hbvless` / `hbssh` gateways; `server/docker-combined/` builds one image with all services |
| `installer/` | Source of the single-file Windows installer |
| `deploy/vps/` | Example deployment of a REALITY-only server |
| `build_installer.ps1`, `build_apk.ps1` | Packaging entry points; they call scripts in `scripts/build/`, which is not included in this repository |

## Building

Windows (from `client/`, with Visual Studio Build Tools, vcpkg and Flutter installed):

```
cargo build --release --lib --features flutter
cd flutter
flutter build windows --release
```

Android: cross-compile the Rust core with `cargo ndk --platform 21 --target aarch64-linux-android build --release --features flutter,hwcodec --lib`
on Linux or WSL, copy it to `flutter/android/app/src/main/jniLibs/arm64-v8a/librustdesk.so`,
then run `flutter build apk --release --target-platform android-arm64 --split-per-abi`.
The Android Xray library (`libxray.so`) is not included in this repository.

## Privacy

Addresses, domains, keys and IDs in the deployment files are placeholders
(`203.0.113.x`, `example.com`, `REPLACE_WITH_...`). Replace them with your own values
before deploying. Never commit real network configuration files or keys.

## License

AGPL-3.0, the same as upstream [RustDesk](https://github.com/rustdesk/rustdesk) and
[RustDesk Server](https://github.com/rustdesk/rustdesk-server).
