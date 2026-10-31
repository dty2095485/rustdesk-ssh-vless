# Forward all named/positional arguments to the maintained packaging entry point.
# Build from a tag worktree, never from a working tree:
#   powershell -File build_apk.ps1 -Worktree D:\RD\build\src-v1.5.1.2 -ReleaseVersion 1.5.1.2
if (!$args) {
    Write-Host 'usage: build_apk.ps1 -Worktree <tag worktree> [-ReleaseVersion <version>] [-VerifyOnly]'
    Write-Host 'see docs/CODE-MANAGEMENT.md section 4'
    exit 2
}
& "$PSScriptRoot\scripts\build\build_apk.ps1" @args
if (!$?) { throw 'Android packaging failed' }