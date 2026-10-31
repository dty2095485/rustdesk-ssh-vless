# 发布索引

按版本号数值升序排列（资源管理器的字母序会把 1.5.0.10 排在 1.5.0.2 前面，以本表为准）。
文件名遵循官方 `rustdesk-<版本>-<架构>` 形式，每个版本一个目录，平台子目录分放。

| 版本 | 平台 | 文件 | SHA256 |
|---|---|---|---|
| 1.5.0.2 | Android arm64 | `android\rustdesk-1.5.0.2-aarch64.apk` | `145618aa1c1aea3c…` |
| 1.5.0.2 | Windows x64 | `windows\rustdesk-1.5.0.2-x86_64.exe` | `bff6a14d2a442e7a…` |
| 1.5.0.3 | Windows x64 | `windows\rustdesk-1.5.0.3-x86_64.exe` | `1ba3cd81148d0138…` |
| 1.5.0.4 | Windows x64 | `windows\rustdesk-1.5.0.4-x86_64.exe` | `16589855c8cda02a…` |
| 1.5.0.5 | Windows x64 | `windows\rustdesk-1.5.0.5-x86_64.exe` | `412a4ef926a4649e…` |
| 1.5.0.6 | Windows x64 | `windows\rustdesk-1.5.0.6-x86_64.exe` | `a561849171e0d67f…` |
| 1.5.0.7 | Windows x64 | `windows\rustdesk-1.5.0.7-x86_64.exe` | `c3f976581b91616d…` |
| 1.5.0.8 | Windows x64 | `windows\rustdesk-1.5.0.8-x86_64.exe` | `990186ab09283bb2…` |
| 1.5.0.9 | Windows x64 | `windows\rustdesk-1.5.0.9-x86_64.exe` | `b91a63981cc04c85…` |
| 1.5.0.10 | Android arm64 | `android\rustdesk-1.5.0.10-aarch64.apk` | `743bf1972032a576…` |
| 1.5.0.10 | Windows x64 | `windows\rustdesk-1.5.0.10-x86_64.exe` | `45d019ab03c4fe9b…` |
| 1.5.0.11 | Docker amd64 | `docker\rustdesk-server-combined-1.5.0.11-x86_64.tar` | `697d3a89d2b096b6…` |
| 1.5.0.11 | Windows x64 | `windows\rustdesk-1.5.0.11-x86_64.exe` | `0780e164d3652f4f…` |
| 1.5.1.1 | Android arm64 | `android\rustdesk-1.5.1.1-aarch64.apk` | `4ce03e90260c034c…` |
| 1.5.1.1 | Docker amd64 | `docker\rustdesk-server-combined-1.5.1.1-x86_64.tar` | `7a9243058de2e098…` |
| 1.5.1.1 | Windows x64 | `windows\rustdesk-1.5.1.1-x86_64.exe` | `2f7b9499cd0cdf27…` |
| 1.5.1.2 | Android arm64 | `android\rustdesk-1.5.1.2-aarch64.apk` | `f12870cd9455b8bd…` |
| 1.5.1.2 | Docker amd64 | `docker\rustdesk-server-combined-1.5.1.2-x86_64.tar` | `1f9950b7fcdf8d04…` |
| 1.5.1.2 | Windows x64 | `windows\rustdesk-1.5.1.2-x86_64.exe` | `9db83305b17ba1de…` |

保留策略：最多 20 个版本，当前 12 个。

未纳入版本索引的历史目录：`1.4.9-v0.1.0-github/`（1.4.9 首发包，保留原名）；`server/`（VPS 部署用的镜像归档，不属于客户端安装包）；`android/`、`windows/ssh/`（私密网络配置 JSON，不随安装包分发）。
