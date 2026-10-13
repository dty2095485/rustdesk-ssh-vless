# RustDesk SSH / VLESS source workspace

当前客户端：RustDesk 1.5.0，自定义发布版本 1.5.0.2。服务端：1.1.17。

## 目录

- `client/`：当前 Windows / Android Flutter 客户端，SSH、VLESS TCP+TLS、REALITY、JSON 参数导入导出。
- `server/`：hbbs、hbbr、hbvless、hbssh 及服务端构建源码。
- `installer/`：Windows 安装器源码与资源。
- `scripts/build/`：构建、打包、版本管理和验证工具。
- `deploy/`：部署及管理页面源码；当前官方 3X-UI 3.9.0 / Xray 26.9.30 升级方案见 `vps1-panel39/`、`vps3/panel39/`。
- `archive/`：旧客户端、服务端参考源码、旧构建上下文与部署方案；不作为当前服务端生产构建入口。

## 构建入口

Windows 打包：`./build_installer.ps1 -KeepExistingNetworkProfiles`。此步骤要求先编译 `client/` 中的 Flutter EXE 和 Rust DLL，不会自动编译它们。

Android：先在 WSL 执行 `scripts/build/build_android_150.sh` 和 `build_xray_android.sh`，再执行 `./build_apk.ps1`。Android Xray 可执行文件的既有构建源保存在 `archive/xray-server-compat/`；这不代表服务器仍使用该定制核心，当前服务端部署使用官方 Xray。

工具链仍安装在 `<workspace>/tools` 及 WSL `/opt`；发布产物仍输出到 `<workspace>/releases`。打包及隐私验证所需真实参数文件必须在本机单独提供，不在此仓库保存。旧构建/诊断脚本保留历史路径，不保证可直接运行。

## 安全与迁移

本目录只整理源码，不包含安装包、编译缓存、私钥、面板数据库及真实网络参数。部署模板中的私人地址、密钥和身份已替换为示例值，部署前需填写私有参数。

`SOURCE-INVENTORY.json` 记录复制来源；`MIGRATION-VERIFICATION.json` 记录整理后文件哈希。原 `<workspace>/work` 和 `old/source` 保留作为本地迁移备份。本次未提交或推送 Git。

迁移仅检查文件完整性和脚本语法，没有重新完成 Windows/Android 全量编译，也没有修改生产 VPS。
