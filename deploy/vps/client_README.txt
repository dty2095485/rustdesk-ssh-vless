# RustDesk 定制客户端（内置 VLESS 配置）

## 版本选择
- **便携版**：`RustDesk.exe` —— 解压即用，无需安装；功能受限（无托盘常驻、锁屏后不可连、无开机自启）。
- **完整安装版**：`RustDesk-setup.exe` —— 双击后进入安装界面（或静默安装：`RustDesk-setup.exe --silent-install`）。安装后可：关闭窗口收进系统托盘、开机自启、锁屏/未登录状态也能被连接、远程操作 UAC 提权窗口等。

## 内置配置（两种版本相同）
- ID 服务器：`your-domain.example`
- VLESS 服务器 / SNI：`nas.your-domain.example`，端口 `443`，UUID 内置
- 自动更新：已禁用
- 设置 → 网络 → VLESS + TCP + TLS 有开关：开=走 VLESS 隧道（隐蔽）；关=官方直连模式

## 注意事项
- Windows SmartScreen 提示"未知发布者"：点"更多信息"→"仍要运行"。
- 防火墙弹窗请选择"允许访问"。
