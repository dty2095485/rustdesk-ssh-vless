# VPS1 专用 443 分流管理

页面管理 VPS1 的 Nginx 443 入口，不修改 3x-ui 的用户、密钥或 Xray 出站路由。
安装时保留现有分流文件原文。规则按表格从上到下匹配，第一条匹配生效。

## 访问

2026-10-02 已启用 HTTPS 域名及随机 URI 入口。完整地址保存在本机
`<workspace>\deploy\vps1-mux-ui\access-private.json` 的 `public_url` 字段，
路径在 `uri_path` 字段。不要只访问域名根路径；根路径和原 `/api/*` 均返回404。
账号、密码未变，仍使用下方本机参数文件中的用户名和密码。

```text
公网 TCP443（SNI vps1.example.com，任意 ALPN）
→ Nginx 127.0.0.1:14443（宝塔站点 HTTPS / 域名证书）
→ HTTP 127.0.0.1:18080（443 分流管理服务）
```

分流表的目标填写 `127.0.0.1:14443`，不要填写 HTTP 管理端口 `18080`。
宝塔站点 `/www/server/panel/vhost/nginx/vps1.example.com.conf` 使用现有证书，
HTTPS 只监听本机14443，反代 Host 保留域名。HTTP 跳转按 `$scheme` 判断，
不能继续按内部端口是否为443判断，否则会发生循环跳转。
后端仅允许显式配置的 HTTPS 来源 `https://vps1.example.com`，并要求本机反代
传入 HTTPS 标识；登录 Cookie 带 Secure/HttpOnly/SameSite，CSRF和跨站保护保留。
管理账号和真实配置不会出现在未登录响应中。
URI 前缀由 Nginx 剥离后转发到管理服务；前端 API 自动沿用入口路径，
HTTPS Cookie 也仅限该路径。随机 URI 是额外防护，不能替代密码认证和 CSRF。
完整入口及 `access-private.json` 不要放在公开仓库、文档或截图中。

原 SSH 隧道访问方式仍可使用：

在 PowerShell 运行下面的 SSH 隧道，并保持窗口打开：

```powershell
ssh -i "<workspace>\.ssh\vps1_id_ed25519.pem" -p 22 -o ExitOnForwardFailure=yes -N -L 127.0.0.1:12080:127.0.0.1:18080 root@203.0.113.10
```

Chrome 打开 `http://127.0.0.1:12080/`。
用户名和随机密码保存在本机 `<workspace>\.ssh\vps1-mux-ui-settings.json`。
这不是 3x-ui 面板，不能使用其账号密码登录。
后端只监听 `127.0.0.1:18080`，不要将该端口暴露到公网。

## 操作

- 新增、修改、启停或移动规则；上方规则优先匹配。
- SNI 支持准确域名、`*.example.com` 和 `*`。ALPN 留空表示任意。
- 默认目标用于所有未匹配的连接，当前为网站 `127.0.0.1:4443`。
- 目标只能是本机 `127.0.0.1:端口` 或 `[::1]:端口`，不能是 443 或管理页自身。
- 端口测试只检查 TCP 可连接，不代表 VLESS/REALITY 认证成功。
- 预览只校验表单并生成配置；应用时备份、执行完整 `nginx -t`、平滑重载并检查新工作进程。
- 应用失败自动恢复原文件；备份可通过页面恢复，最多保留 20 份。
- 外部修改文件会触发冲突保护，不允许页面静默覆盖。修改入口应统一使用该页面。

2026-10-02 已统一 NAS 入口：`nas.example.com` 规则 ALPN 留空，所有连接进入 Xray `18444`，
有效 VLESS 请求走 RustDesk，浏览器通过 Xray fallbacks 进入网站 `4443`。
不要再添加 NAS 的浏览器直送网站规则；VPS1 已部署立即响应头的服务端兼容补丁，
原有 VLESS TLS 客户端不需要升级或改代码。ALPN 不是认证。
详情见 `<workspace>\deploy\vps1-tls-fallback\README.md`。
同一个 REALITY 入站内按 UUID 分流仍在 3x-ui/Xray 管理。

## 位置与维护

- VPS 程序：`/opt/rustdesk-mux-ui`
- 状态、登录信息和备份：`/var/lib/rustdesk-mux-ui`（仅 root 可读）
- 生产分流文件：`/www/server/panel/vhost/nginx/tcp/vless_mux.conf`
- 服务：`rustdesk-mux-ui.service`
- 日志：`journalctl -u rustdesk-mux-ui -n 50 --no-pager`
- HTTPS 域名部署记录：`/var/lib/rustdesk-mux-ui/https-domain.json`
- 本次受保护的原文件备份：`/var/lib/rustdesk-mux-ui/https-backup-20261002-145601-b023abdb`
- URI 部署记录：`/var/lib/rustdesk-mux-ui/uri-domain.json`
- URI 修改前备份：`/var/lib/rustdesk-mux-ui/uri-backup-20261002-150410-a11f94a4`
- 本次未改客户端、Xray 核心或 NAS/REALITY/test 规则；只改管理服务 HTTPS 来源
  校验、该宝塔站点及新增 vps1 分流规则。

停用管理页只需 `systemctl disable --now rustdesk-mux-ui`，不会停止 Nginx 或 RustDesk。
