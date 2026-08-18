# RustDesk SSH+VLESS

[English](README.md) | 简体中文

基于 [RustDesk](https://github.com/rustdesk/rustdesk) 二次开发的自建远程桌面方案,在官方协议基础上加了两种额外的传输方式:

- **SSH 隧道**——客户端和中转服务器用内置的共享 ed25519 身份互相认证,把 RustDesk 协议包在 SSH 通道里传输。
- **VLESS + TCP + TLS**——流量走 VLESS 网关(`hbssh`)转发,适合在限制较多的网络环境下使用,域名/SNI 看起来和普通 HTTPS 流量一样。

客户端还加了一个合并版的配置导入/导出(设置 → 网络 →"Import/export all config"):把 ID/中继/API/key 这些服务器设置,连同 VLESS 和 SSH 设置一起打进一个 JSON 文件,而不是官方原版那种只能通过剪贴板单独复制 ID/中继/API/key 的方式。

## 目录结构

| 路径 | 是什么 |
|---|---|
| `client/` | RustDesk 桌面客户端(Rust 核心 + Flutter 界面),基于官方 fork 出来并加了 SSH/VLESS 支持 |
| `server/` | RustDesk 中转/信令服务器(`hbbs`/`hbbr`),基于官方 fork |
| `hbssh-deploy/` | 独立的 SSH 网关(`hbssh`),负责把 SSH 隧道桥接到中转服务器的内部端口 |
| `nas-arm64-context/`、`r2-context/` | 把中转服务器 + SSH 网关打包成容器运行用的 Docker 构建上下文(分别对应 ARM64 NAS 和通用 x86_64) |
| `installer/` | Windows 单文件安装包的引导程序(C#),被 `build_installer.ps1` 调用 |
| `scripts/nas/` | 给 NAS 上跑的中转服务器做基准测试/巡检/监控用的辅助脚本 |
| `deploy/vps/` | 搭建中转服务器过程中留下的 VPS 部署/诊断脚本迭代历史(留作参考,没有整理成单一的"官方"脚本) |

## 构建时配置

这个 fork 早期版本把 SSH 身份、VLESS UUID、中转域名直接硬编码在源码里。现在已经全部改成构建时通过环境变量注入,仓库里的源码只保留占位符。想指向自己的服务器基础设施,构建前设置以下变量:

**客户端 / 服务端(Rust,通过 `cargo build`,可以用 `set VAR=value`,或者写一份不提交的 `.cargo/config.toml` `[env]` 配置):**

| 变量 | 作用 |
|---|---|
| `RD_RENDEZVOUS_SERVER` | 信令/中继域名(客户端默认的 ID 服务器 + relay-server 选项) |
| `RD_RENDEZVOUS_PUBKEY` | 信令服务器的公钥(`RS_PUB_KEY`) |
| `RD_RELAY_KEY` | 直连模式下的旧版 `key` 选项 |
| `RD_VLESS_SERVER` | VLESS 网关地址 / SNI |
| `RD_VLESS_UUID` | VLESS UUID |
| `RD_SSH_USERNAME` | 内置 SSH 用户名(客户端) |
| `RD_SSH_PUBLIC_KEY` | 内置 SSH 公钥(客户端默认值 + 服务端的授权公钥) |
| `RD_SSH_PRIVATE_KEY` | 内置 SSH 私钥(客户端) |
| `RD_SSH_HOST_PRIVATE_KEY` | SSH 网关的主机密钥(服务端 / `hbssh-deploy`) |

**Flutter 界面**,通过 `flutter build ... --dart-define=RD_VLESS_SERVER=... --dart-define=RD_VLESS_UUID=...`

不设置这些变量的话,客户端/服务端依然能正常编译,但只带空的/占位符身份——SSH 网关会拒绝启动(报错 `Invalid built-in SSH host key`),VLESS 设置里也只会显示示例值,直到你自己配置。

## 这个仓库里故意不包含的东西

- `target/`、`build/`、`.dart_tool/` 等编译缓存
- 编译出来的二进制文件和 Docker 镜像 tar 包(`hbbs`、`hbbr`、`hbssh`、`hbvless`、`*.tar`)
- SSH 私钥、TLS 证书、`known_hosts`
- 个人部署留下的痕迹:真实域名/IP、VPS 端的配置备份、调试中转服务器时留下的截图和日志

## 怎么编译

1. 客户端:参考 `client/README.md`(官方 RustDesk 的构建文档同样适用),再加上上面那些环境变量。
   核心 DLL **必须**用 `cargo build --release --locked --features flutter` 编译(`flutter` 不在 Cargo.toml 的 `default` feature 列表里)——只跑 `cargo build --release` 会悄悄把整个 UI 依赖的 flutter_rust_bridge FFI 层编译掉,产物看起来正常,体积却小了将近 19MB,实际是没接上界面的坏包。
2. 服务端:在 `server/` 目录下 `cargo build --release`,同样加上上面的环境变量。
3. Windows 自解压 exe:`build_portable.ps1`(脚本开头写死了本机路径,换机器要自己改)。这个脚本调用的是
   RustDesk 官方自带的打包工具 `client/libs/portable/`(需要 Python 3,并在那个目录下
   `pip install -r requirements.txt`)——和官方正式发布版用的是同一套工具,编出来的是原生 Rust exe。
   `installer/` + `build_installer.ps1`(用 C#/`csc.exe` 手写的自解压 stub)保留下来仅供参考,**不建议再用**:
   这种打包方式在一台确认是普通 x64 的 Windows 11 电脑上被 Windows 智能应用控制(Smart App Control)拦截了
   (对比过换成官方同款打包方式之后能正常装,确认了这一点)——没签名、加上这种不常见的自解压结构,两个因素都在起作用,
   换成官方打包工具只解决了后一半。
4. 服务端+网关四合一镜像(`hbbs`+`hbbr`+`hbvless`+`hbssh` 打进一个容器):
   有 Docker 的话直接用 `server/docker-combined/Dockerfile`;
   没有本地 Docker 引擎的话,用 `server/docker-combined/build-offline-image.sh`,靠 [crane](https://github.com/google/go-containerregistry) 直接构建并推送到镜像仓库。

## 已发布的产物

- Windows 安装包:见 [Releases](../../releases)——用占位符连接配置编译的,没有内置真实服务器信息;装完之后自己通过 设置 → 网络 →"Import/export all config" 导入你自己的配置,或者用上面的环境变量重新编译。
- 服务端+网关四合一镜像:`ghcr.io/dty2095485/rustdesk-server-combined:latest`(同样是占位符构建,没有个人配置;通过容器的 `RELAY`、`VLESS_UUID`、`VLESS_CERT`、`VLESS_KEY`、`SSH_AUTHORIZED_KEYS` 环境变量/挂载来配置)。
  也以 `rustdesk-server-combined-docker-x86_64.tar` 的形式挂在 [Releases](../../releases) 里——不方便连镜像仓库的机器可以直接下载这个离线包:`docker load -i rustdesk-server-combined-docker-x86_64.tar`。
