# VPS3 RustDesk REALITY

服务地址：203.0.113.30，公网 REALITY TCP 443。系统 SSH 22 保留。
官方 RustDesk TCP 21115–21119、UDP 21116、Web UI 和网关端口均已对外隔离。
TLS 网关只在回环地址运行，以满足现有合并镜像的监督和健康检查；不提供公网 TLS 模式。

VPS 配置目录：`/opt/rustdesk-server`，容器：`rustdesk-server`。
启动命令：`cd /opt/rustdesk-server && docker compose up -d`。
日志：`docker logs --tail 100 rustdesk-server`。

客户端在 ID/中继服务器设置中填写：

- ID 服务器：`203.0.113.30`
- 中继服务器：`203.0.113.30`
- Key：本机 `<workspace>\.ssh\vps3-client-settings.json` 的 `rustdesk_key`

开启 VLESS，选择 REALITY：

- 地址 `203.0.113.30`，端口 `443`
- SNI `www.nvidia.com`（借站目标，不是服务器地址）
- UUID、公钥、Short ID：从上述参数文件读取
- 指纹 `chrome`，Flow `xtls-rprx-vision`
- 禁用 UDP，强制中继；关闭 VLESS 后不会连接 VPS3 的官方端口

Web UI 通过隧道访问：

```powershell
ssh -i "<workspace>\.ssh\nodemach_key.pem" -p 22 -o ExitOnForwardFailure=yes -N -L 127.0.0.1:12053:127.0.0.1:2053 root@203.0.113.30
```

保持 PowerShell 窗口打开；隧道建立后没有输出是正常现象。
在运行上述命令的同一台电脑上，用 Chrome 打开完整地址：

```text
http://127.0.0.1:12053/REPLACE_WITH_PANEL_PATH
```

不能只访问 `http://127.0.0.1:12053/`，根路径会返回 404。
`ERR_CONNECTION_REFUSED` 表示本机隧道没有监听，请检查 SSH 窗口的报错。
用户名、密码在本机 `<workspace>\.ssh\vps3-client-settings.json` 的
`panel_username`、`panel_password` 字段，不在客户端网络 JSON 中。
若重新部署或修改面板路径，以该参数文件的 `panel_path` 为准。

服务器生成了独立的 RustDesk Key 和 REALITY 密钥，没有复制 VPS1 的认证配置。
REALITY 专用 UUID 只允许访问 `127.0.0.1:22115–22117`。
未认证的目标网站回落连接有独立限速；已认证 RustDesk 通道不受该回落限速影响。

## REALITY 443 代理上网

同一个入站包含两个独立用户，无需新增第二个 443 入站：

- `rustdesk-client`：原 UUID 不变，只能访问内部 RustDesk TCP 22115–22117。
- `proxy-internet`：独立 UUID，公网流量走 `direct`；私网和回环地址被阻止。

代理客户端导入本机 `<workspace>\deploy\vps3\VPS3-proxy-link.txt` 中的 VLESS 链接。
完整代理参数：`<workspace>\deploy\vps3\VPS3-proxy-settings.json`。
不要将这个代理 UUID 填入 RustDesk；RustDesk 继续使用 `VPS3-network.json`。
两个用户共用 REALITY SNI、公钥和 Short ID，但 UUID 和用途不同。
上述代理文件包含认证凭据，请勿公开。

服务器参数文件：`/opt/rustdesk-server/proxy-settings.json`。
此次变更前的面板数据库备份位于 `/opt/rustdesk-server/x-ui-data/x-ui-before-proxy-*.db`。
