# 代码管理规范

本文件是 `rustdesk-ssh-vless` 的唯一代码管理标准。凡与本文件冲突的习惯、脚本或旧文档，以本文件为准。

## 1. 仓库职责

| 仓库 / 目录 | 职责 | 是否可发布 |
|---|---|---|
| `github-release`（本仓库，GitHub `dty2095485/rustdesk-ssh-vless`） | **唯一权威源码**：`client/`、`server/`、`installer/`、`deploy/` | 是 |
| `work\rustdesk-ssh\rustdesk` | 上游镜像 + 合并工作区（`origin` = 官方 rustdesk），只用于把官方 tag 合并进 fork | 否 |
| `work\rustdesk-1.5.0-integration` | 2026-10-03 迁移工作树 | 否（归档） |
| `releases\<版本>\` | 本地发布归档（安装包、manifest、SHA256SUMS） | —（二进制不入 git） |

规则：

1. 只能从**本仓库的 tag** 构建发布包，不得从任何工作树直接构建。
2. 官方源码只从 `origin`（官方 rustdesk）获取，不在本仓库内改上游文件以外的东西。
3. 私密材料（`.ssh`、`.sshkeys`、`*-network.json`、`*client-settings*.json`、密钥）永不入库，`.gitignore` 已覆盖。

## 2. 分支模型

| 分支 | 用途 | 规则 |
|---|---|---|
| `master` | 发布分支 | 始终可构建；每次发布打 tag |
| `feature/<主题>` | 单点改动 | 从 `master` 开，合并后删除 |
| `archive/<旧名>` | 历史快照 | 只读，不再合并 |

- 合并上游：`git merge --no-ff <上游tag>`，保留上游历史，不用 squash。
- 禁止在 `master` 上直接做“一次性大合并”提交后又改写历史。

## 3. 版本号与 tag

- 版本号 = 官方版本 + `.` + 修订号，例如 `1.5.1` + `.2` → `1.5.1.2`（四段，**不声称符合 SemVer**）。
- 上游 tag 保持原样（`1.5.0`、`1.5.1`，无 `v` 前缀）。
- fork 发布 tag 统一为 `v<版本>`（`v1.5.1.2`），**annotated**，注释里写：官方版本、上游 commit、本版一句话摘要。
- 同一版本号不得复用；发布后发现缺陷，只能递增修订号（`1.5.1.3`），并像 1.5.1.1 那样在 CHANGELOG 标 `[superseded]`。

## 4. 发布流程（六步，缺一不可）

1. **合上游**：`master` 合入目标官方 tag，解决冲突时禁止整文件 `checkout --ours`；冲突文件必须与“上一次发布的 fork 源码”三方比对后再定。
2. **定版本**：在 `Cargo.toml` / `pubspec.yaml` / `build.gradle` 写入版本（数值版本用于 Windows EXE 与 APK `versionCode`）。
3. **打 tag**：`git tag -a v<版本> -m "..."`，推送到 GitHub。
4. **从 tag 构建**：
   ```
   git worktree add D:\RD\build\src-<版本> v<版本>
   powershell -File scripts\build\build-windows.ps1 -Source D:\RD\build\src-<版本> -BuildName 1.5.1 -BuildNumber 2
   powershell -File scripts\build\build_apk.ps1     -Source D:\RD\build\src-<版本>
   ```
   脚本必须校验 `git describe --exact-match`，源码不是 tag 就拒绝构建。
5. **归档与校验**：产物进 `D:\RD\releases\<版本>\<平台>/`，文件名 `rustdesk-<版本>-<架构>.<扩展名>`；生成 `manifest.json`、`SHA256SUMS.txt`，并重复校验：载荷文件齐全、私密参数扫描、APK 签名与原生库哈希、Docker 容器健康检查。
6. **发布与记录**：GitHub Release（附 `SHA256SUMS.txt` 与 release notes）→ 更新本仓库 `CHANGELOG.md`、`docs/releases/<版本>.md`、`releases/versions-index.json`、`INDEX.md`。

## 5. 提交规范

- 采用 Conventional Commits：`feat(scope): ...`、`fix(clipboard): ...`、`docs: ...`、`build: ...`、`chore: ...`。
- 一个提交只做一件事，且必须能独立编译。
- 上游补丁类提交在正文注明来源 PR 号（如 `#16329`）。
- 署名与 DCO：`git commit -s`（与上游 `docs/CONTRIBUTING.md` 一致）。

## 6. 变更记录规则

- `CHANGELOG.md` 遵循 Keep a Changelog 的 `Added / Changed / Deprecated / Removed / Fixed / Security` 分类。
- 一节对应一个已发布版本，日期用发布日期；被取代或撤回的版本保留条目并标 `[superseded]` / `[withdrawn]`，不删除历史。
- 每条尽量写成用户可见的结果（症状 + 修复），不写实现细节。
- 已知限制（未在真机验证、未覆盖的场景）必须在该版本的 `docs/releases/<版本>.md` 里写明。

## 7. 归档与清理

- 旧工作树不删除：加 `ARCHIVED.md` 说明“仅历史、不可用于构建”，或移动到 `archive/` 下的明确路径。
- 删除任何源码树、备份或发布产物前，先确认它是否是某个 tag 的唯一副本；`releases\<版本>\` 的归档不因“保留最近 N 版”策略自动删除（现行 `keep_max` 已放宽）。
- 永久删除（`Remove-Item`）会绕过回收站，清理前先 `BACKUP` 到 `backups-local`。

## 8. 禁止事项

1. 从会漂移的工作树发版（1.5.1.1 事故根因）。
2. 用 `git checkout --ours/--theirs` 整文件解决“两边都改过”的冲突。
3. 把发布说明、版本索引只留在 `D:\RD\releases` 而不入库。
4. 在 `master` 上改写已推送历史，或复用已发布的版本号/tag。
5. 把地址、UUID、私钥、面板密码写进源码或安装包。
