# 给 Claude / AI 编码助手看的说明

这是 RustDesk 的一个自建 SSH+VLESS 二次开发版本(详见 [README.zh-CN.md](README.zh-CN.md))。在这个仓库里做修改前,先了解这几条硬性规则。

## 绝对不能做的事

- **不要把真实的域名、IP、UUID、私钥硬编码进源码。** `client/libs/hbb_common/src/config.rs`、`client/flutter/lib/desktop/pages/desktop_setting_page.dart`、`server/src/ssh.rs`、`hbssh-deploy/src/main.rs` 里的连接身份信息(SSH 私钥、VLESS UUID、中转域名)全部是通过 `option_env!()` / `String.fromEnvironment()` 在构建时从环境变量注入的,源码里只留占位符(`your-domain.example`、全零 UUID、空字符串)。改动这几个文件时,新增的默认值也必须是占位符,不能是真实值——这个仓库本来就是因为原来把私钥直接写进源码才需要重新整理的,详见 `README.md` 的 "Build-time configuration" 一节。
- **不要往仓库里加真实的 `.pem`/`.key`/`id_ed25519*`/`known_hosts`/证书**,`.gitignore` 已经挡了常见后缀,但改脚本或加新文件时自己也留意一下。
- **不要往仓库里加编译产物**(`target/`、`build/`、`.dart_tool/`、`*.exe`、`*.dll`、`*.tar` 等),这些是特意排除的,详见 `.gitignore`。`server/ui/setup/service/nssm.exe` 是唯一的例外(上游自带的开源服务管理工具)。

## 编译时容易踩的坑

- **客户端核心 DLL 必须带 `--features flutter` 编译**:`cargo build --release --locked --features flutter`。`client/Cargo.toml` 的 `default` feature 里没有 `flutter`,光跑 `cargo build --release` 会把整个 flutter_rust_bridge FFI 桥接层编译掉——不报错,DLL 也能生成,但体积小了近 19MB,界面完全调不通核心逻辑。这个坑已经真实踩过一次。
- 服务端(`server/`)没有这个问题,`server/Cargo.toml` 没有 `[features]` 门控,普通 `cargo build --release` 就够。
- 改了 `client/src/lang/*.rs`(翻译表)之后,**必须重新编译核心 DLL**,不是单纯重新跑 `flutter build windows` 就行——`translate()` 是 Rust FFI 函数,翻译表编译进的是 DLL,不是 Dart 代码。
- Windows 装机包靠 `build_installer.ps1` 打包,它只是把已经编译好的 `flutter/build/windows/.../Release/*` 和 `target/release/librustdesk.dll` 打进一个自解压 exe,不会帮你跑 cargo/flutter build,顺序错了会打出旧内容。

## 本地化(`client/src/lang/*.rs`)

新增界面文字用句子式大小写(不是 Title Case),键本身就是英文显示文本,只有需要和显示文本不同(比如带 `_tip` 后缀)时才需要在 `en.rs` 里单独写。新键要加到 `template.rs`(值填 `""`)以及**每一个** `src/lang/*.rs` 文件末尾(没翻译先填 `""`,回退显示英文键名)。`cn.rs`(简体中文)建议顺手填上真实翻译,不要留空,不然界面上会中英文混杂。

## Docker 镜像构建

`server/docker-combined/` 下有两条路:有 Docker 引擎就直接用 `Dockerfile`(s6-overlay,支持进程崩溃自动重启);没有 Docker 引擎(比如只有 WSL 但没装 docker)就用 `build-offline-image.sh`,靠 [crane](https://github.com/google/go-containerregistry) 直接把编译好的二进制拼进 `ubuntu:26.04` 基础镜像并推送,不需要本地 daemon,但配套的 `entrypoint-offline.sh` 是手写的简单 supervisor,没有自动重启逻辑。

## 更多细节

`client/AGENTS.md`、`server/AGENTS.md` 是上游 RustDesk 项目自带的编码规范(Rust 风格、Tokio 使用规则、本地化细节等),改这两个子目录下的代码时同样适用,以那两份为准。
