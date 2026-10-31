# Mirror the release index into the repository.
#
# Binary artifacts stay outside git; the index and the human-readable order
# (versions-index.json / INDEX.md) are versioned so a clone can see every
# published build. Run this after each release, then commit docs/releases/.
param(
    [string]$ReleasesRoot = $env:RD_RELEASES_ROOT,
    [string]$Dest
)
$ErrorActionPreference = 'Stop'
if (!$ReleasesRoot) { $ReleasesRoot = 'D:\RD\releases' }
if (!$Dest) { $Dest = Join-Path $PSScriptRoot '..\..\docs\releases' }
$Dest = [IO.Path]::GetFullPath($Dest)
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$pairs = @(
    @{ From = Join-Path $ReleasesRoot 'versions-index.json'; To = Join-Path $Dest 'versions-index.json' },
    @{ From = Join-Path $ReleasesRoot 'INDEX.md';           To = Join-Path $Dest 'INDEX.md' }
)
foreach ($pair in $pairs) {
    if (!(Test-Path -LiteralPath $pair.From)) { throw "missing release index file: $($pair.From)" }
    Copy-Item -LiteralPath $pair.From -Destination $pair.To -Force
    Write-Host "mirrored $(Split-Path $pair.From -Leaf) -> $($pair.To)"
}

$index = Get-Content -LiteralPath (Join-Path $Dest 'versions-index.json') -Raw | ConvertFrom-Json
$latest = $index.versions[-1]
Write-Host "LATEST VERSION: $($latest.version)  ($($latest.artifacts.PSObject.Properties.Name -join ', '))"
