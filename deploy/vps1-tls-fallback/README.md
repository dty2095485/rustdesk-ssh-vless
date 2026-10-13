# VPS1 Xray TCP+TLS 网站回落

> 当前状态更新：已升级官方 3X-UI 3.9.0 / Xray 26.9.30，移除服务端响应头补丁。
> TLS 客户端需要 1.5.0.2 或包含标准握手修复的版本。下文兼容核心部署说明属于历史记录，
> 不要按历史步骤重新应用补丁。当前构建、测试和回退说明见 `../vps1-panel39/README.md`。

2026-10-02 已部署。TLS 入站复用现有 `rustdesk-server` 容器内的 Xray，
参数保存在 3x-ui 中。NAS 的公网入口仍为 `nas.example.com:443`。

## 当前统一入口拓扑

```text
公网 TCP 443 / Nginx stream
├─ nas.example.com，所有 ALPN（包括不提供 ALPN）→ Xray 127.0.0.1:18444
│  ├─ 有效 RustDesk UUID → 内部 hbbs/hbbr 22115 / 22116 / 22117
│  └─ 普通浏览器 → fallbacks
│     ├─ HTTP/1.1 → 127.0.0.1:18081
│     └─ HTTP/2   → 127.0.0.1:18082（h2c）
│        → Nginx 校验证书的 HTTPS 反代 → 127.0.0.1:4443 网站
├─ rd.example.com → 原 REALITY 127.0.0.1:10443（参数及路由保持）
└─ 默认 → 原网站 127.0.0.1:4443
```

NAS 在外层不再按 ALPN 分流，也不再进入原 hbvless。进入 Xray 后，有效 VLESS
请求走 UUID 认证和严格端口路由；不符合 VLESS 的浏览器请求走 `fallbacks`。
Xray 内部 ALPN 只选择 HTTP/1.1 或 HTTP/2 回落后端，不是认证。网站公网连接始终使用 TLS。
网站原配置未修改，新增明文 HTTP/h2c 端口只监听回环地址。
`127.0.0.1:443` 是公网 stream 入口自身，不能作为回落目标，否则会回环；
现有 HTTPS 网站实际监听 `127.0.0.1:4443`。

## 客户端

按用户要求，原有支持 VLESS TLS 的客户端无需改代码、重编译或升级；
仍使用原 VPS1 TLS 参数连接 `nas.example.com:443`，参数 JSON 未修改。

旧客户端先等 `[0,0]` VLESS 响应头才发送 RustDesk 首包，原版 Xray 将响应头
与首个下行数据合并，会与 hbbs/hbbr 互等。本次改为服务端兼容补丁：
仅 `in-18444-tcp` 入站、`rustdesk-tls-client` 已认证用户、TCP、空 flow、
TLS 连接立即发送响应头；其他入站/用户、REALITY/Vision 和浏览器回落保持原逻辑。
测试候选入站也允许此行为；候选已停止，未开放公网测试端口。

之前制作的客户端握手修复版不再是使用此入口的前提；没有在两台电脑安装或
替换客户端。本次完成协议测试，不等同于两台实际电脑的完整远控交互测试。
原 hbvless 服务保留用于回滚，但 NAS 公网 443 不再路由到它。

## 服务端兼容核心与镜像

- 源码：`<workspace>\work\xray-server-compat`，基于官方 Xray 26.9.9，
  commit `52a412d9e2f5c2a5142b1b4e2ab3771dacb8b120`。
- WSL 使用 Go 1.27.1 构建，`CGO_ENABLED=0`；入站范围和编码测试通过。
- 核心 SHA256：`99c01b48cdb210ea9c264d92932e4d8e980656b591b2354d040ac7060619f73b`。
- 现有运行容器的 `/app/bin/xray-linux-amd64` 已替换；只重启了共享 Xray/UI，
  hbbs/hbbr/hbvless/hbssh 进程未重启，面板生成配置校验值保持完全相同。
- 已构建镜像 `rustdesk-server-combined:tls-compat-20261002`，生产 Compose 的
  `.env` 中 `IMAGE_TAG` 已指向该镜像；未额外重建当前容器。
- 镜像构建定义：`/opt/rustdesk-tls-fallback/Dockerfile.compat`；上下文只包含
  兼容核心，不包含私密参数或数据库。
- 普通容器重启会保留修复；后续 Compose 使用现有兼容镜像启动，不要使用
  原 `Dockerfile.runtime` 加 `--build` 覆盖它。3x-ui 手动更新 Xray 也会覆盖补丁。
- 兼容状态及原程序备份：`/var/lib/rustdesk-tls-fallback/compat-core.json`
  及其记录的 `compat-core-*` 目录。

## 参数管理和位置

- 3x-ui 入站：`RustDesk TLS fallback - NAS :443`，本机端口 `18444`。
  管理 UUID、证书、ALPN 和回落目的地；不要将监听地址改为公网。
- TLS `fallbacks` 默认目的地 `127.0.0.1:18081`；ALPN `h2` 目的地
  `127.0.0.1:18082`；两项均 `xver: 0`，不设置 path。
- 网络入口规则继续使用专用 443 分流管理页面，访问方法见
  `<workspace>\deploy\vps1-mux-ui\README.md`。
- Nginx 分流：`/www/server/panel/vhost/nginx/tcp/vless_mux.conf`。
- 新增网站回落反代：`/www/server/panel/vhost/nginx/rustdesk-tls-fallback.conf`。
- 脚本：`/opt/rustdesk-tls-fallback`；私密状态和备份：
  `/var/lib/rustdesk-tls-fallback`，仅 root 可读。
- 3x-ui 数据库仍在现有容器 `/etc/x-ui/x-ui.db` 的原绑定目录，未换镜像。
- 原网站、REALITY、代理上网出站、SSH 2222 和服务器 SSH 22 保持。

新增 TLS UUID 只允许 RustDesk。逻辑目标 `21115`、`21116`、
`21117 / 443 / 8443` 固定重定向到本机 `22115`、`22116`、`22117`；
不允许访问 SSH 或任意互联网地址。不要删除配套的严格路由/出站白名单。

## 验证和回滚

本机只读公网测试：

```powershell
& "C:\Program Files\Python312\python.exe" <workspace>\deploy\vps1-tls-fallback\probe.py --http2 --relay-aliases --legacy-order
```

已通过：HTTP/1.1、HTTP/2、无 ALPN 网站回落，三种 ALPN 的两个注册端口，三个中继目标别名
的双向数据校验，错误 UUID 隔离，禁止 SSH22；真实 RustDesk Rust 传输代码的公网
注册和双向中继。尚不等同于用户升级后的完整远控交互测试。
客户端响应流的 10 项单元测试及安装包资源/DLL一致性、隐私参数扫描也已通过。
私有候选和公网 443 的旧客户端兼容性均为 `true`。`--legacy-order` 强制每个注册、
中继会话先收到精确 `[0,0]` 才发送业务数据；不使用跳过旧兼容结果的 `--xray-only`。
新版客户端传输及 主站/nas/rd 三个域名网站回归也通过。

在 VPS1 回滚时严格按顺序：

```sh
python3 /opt/rustdesk-tls-fallback/switch_mux.py rollback
python3 /opt/rustdesk-tls-fallback/compat_core.py rollback
python3 /opt/rustdesk-tls-fallback/promote.py rollback
python3 /opt/rustdesk-tls-fallback/stage.py rollback
```

第一步恢复原分流；第二步恢复原 Xray 二进制及 Compose 镜像选择；第三步仅删除
本次新增的 TLS 面板记录及路由，保留原配置和累计流量；第四步移除新增的回落反代。
若页面或文件已被人工改动，脚本会拒绝静默
覆盖，需先检查冲突。第二步会短暂重启共享 Xray，REALITY/代理会话可能重连一次。

配置备份：`production-20261002-080742-e7cbc326`；前期测试备份：
`stage-20261002-074347-286cdb8c`，均位于 VPS `/var/lib/rustdesk-tls-fallback`。
