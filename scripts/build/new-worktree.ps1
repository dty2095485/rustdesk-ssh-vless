# Create a build worktree from a release tag.
#
# The release standard requires every package to be built from a tag, never
# from a working tree. This helper creates that worktree and refuses anything
# that is not an exact tag.
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$Path,
    [string]$RepoRoot
)
$ErrorActionPreference = 'Stop'
if (!$RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
if (!$Path) { $Path = Join-Path 'D:\RD\build' "src-$Tag" }

Push-Location $RepoRoot
try {
    & git rev-parse --verify --quiet "refs/tags/$Tag" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "tag not found in $RepoRoot : $Tag" }
    if (Test-Path -LiteralPath $Path) { throw "worktree path already exists: $Path" }
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    & git worktree add --detach $Path $Tag 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git worktree add failed (exit $LASTEXITCODE)" }
    $exact = (& git -C $Path describe --tags --exact-match 2>$null)
    if ($exact -ne $Tag) { throw "worktree is at '$exact', expected '$Tag'" }
    $dirty = (& git -C $Path status --porcelain 2>$null)
    if ($dirty) { throw 'fresh worktree is unexpectedly dirty' }
    Write-Host "WORKTREE READY: $Path (tag $Tag)"
    Write-Host "  client source: $Path\client"
} finally {
    Pop-Location
}
