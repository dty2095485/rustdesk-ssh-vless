# RustDesk VLESS / SSH

[English](README.md)

基于 RustDesk 1.5.0 客户端和 RustDesk Server 1.1.17 的分支版本。客户端可以通过
SSH 隧道或 VLESS（TCP+TLS 或 REALITY）连接 RustDesk ID / 中继服务器，网络设置
可以导出为 JSON 文件，也可以从 JSON 文件导入。

当前版本：[1.5.0.11](https://github.com/dty2095485/rustdesk-ssh-vless/releases/tag/v1.5.0.11)

## 下载

安装包在 [Releases](https://github.com/dty2095485/rustdesk-ssh-vless/releases) 页面：

- **Windows x64**：单文件安装程序。未签名，运行时可能出现安全警告。
- **Android ARM64**：APK。使用 REALITY 需要 Android 7（API 24）及以上。

安装包不内置任何服务器地址、密钥或 SSH 凭据。安装后请自行填写，或导入网络配置
JSON 文件。

## 目录结构

| 路径 | 内容 |
|---|---|
| `client/` | Windows / Android 客户端：Rust 核心和 Flutter 界面，支持 SSH、VLESS TCP+TLS、REALITY 及 JSON 导入导出 |
| `server/` | `hbbs`、`hbbr` 以及 `hbvless` / `hbssh` 网关；`server/docker-combined/` 用于构建包含全部服务的单一镜像 |
| `installer/` | Windows 单文件安装程序的源码 |
| `deploy/vps/` | 仅使用 REALITY 的服务器部署示例 |
| `build_installer.ps1`、`build_apk.ps1` | 打包入口；它们调用 `scripts/build/` 中的脚本，该目录未包含在本仓库中 |

## 编译

Windows（在 `client/` 目录下，需要 Visual Studio Build Tools、vcpkg 和 Flutter）：

```
cargo build --release --lib --features flutter
cd flutter
flutter build windows --release
```

Android：在 Linux 或 WSL 中用 `cargo ndk --platform 21 --target aarch64-linux-android build --release --features flutter,hwcodec --lib`
交叉编译 Rust 核心，复制到 `flutter/android/app/src/main/jniLibs/arm64-v8a/librustdesk.so`，
再运行 `flutter build apk --release --target-platform android-arm64 --split-per-abi`。
Android 使用的 Xray 库（`libxray.so`）不包含在本仓库中。

## 隐私

部署文件中的地址、域名、密钥和 ID 都是占位符（`203.0.113.x`、`example.com`、
`REPLACE_WITH_...`），部署前请替换为自己的值。不要把真实的网络配置文件或密钥提交到仓库。

## 许可证

AGPL-3.0，与上游 [RustDesk](https://github.com/rustdesk/rustdesk) 和
[RustDesk Server](https://github.com/rustdesk/rustdesk-server) 相同。
