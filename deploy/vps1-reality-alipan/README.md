# VPS1 REALITY / 阿里云盘 SNI

公网服务器地址仍为 VPS1 IP，客户端端口仍为443。SNI 为 `www.alipan.com`；
不要把连接地址填写成阿里云盘域名，也不要使用内部19443端口。

- 公网443匹配 `www.alipan.com`（任意 ALPN），转到127.0.0.1:19443。
- 3x-ui入站端口为19443，REALITY目标为www.alipan.com:443，允许SNI为www.alipan.com。
- 原三个用户的 UUID、密钥、Short ID、Vision和出站路由不变。
- 两个代理用户仍走原远端VLESS节点；rustdesk-client仅允许内部22115–22117。
- rd.example.com直接分到127.0.0.1:4443，保留面板HTTPS和隐藏URI。
- TLS nas.example.com、SSH2222、网站和VPS3配置不变。旧10443监听已关闭。

完整客户端参数位于同目录被忽略的 `client-parameters-private.json`；
导入客户端使用 `<workspace>\releases\windows\ssh\VPS1-network.json`。
该JSON保留原TLS默认模式，完整REALITY配置已补齐，可在客户端切换到REALITY。
不要公开参数JSON，它包含访问凭据。安装包和源码没有内置新的真实参数。

服务器部署脚本：/opt/rustdesk-tls-fallback/migrate_reality_alipan.py
迁移记录与备份位置：/var/lib/rustdesk-reality-alipan/active.json

失败自动回滚：脚本在生产切换中捕获异常时仅恢复被修改的入站字段和分流规则，
不以整库覆盖方式恢复密码、用户或流量统计。完整数据库快照仅供人工灾难恢复。

已验证：隔离候选和公网443的三个用户通信、原代理出站、RustDesk注册、
双向中继、越权目标拒绝、普通TLS探测证书和H2，以及rd面板登录页。
此验证不等于人工完成图形远控和面板账号登录。
