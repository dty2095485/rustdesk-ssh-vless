# Publish a release to GitHub: asset safety check and upload in one step.
#
#   powershell -File scripts\build\publish_release.ps1 -Version 1.5.3.1
#   powershell -File scripts\build\publish_release.ps1 -Version 1.5.3.1 -DryRun
#
# This is the only supported way to put files on a GitHub Release. Steps:
#   1. read releases\<Version>\manifest.json; client artifacts (windows,
#      android) are published, server/docker artifacts are NEVER published
#      (hbssh embeds the SSH host private key at build time)
#   2. every file must exist and match the sha256 recorded in the manifest
#   3. SHA256SUMS.txt is regenerated for exactly the published files
#   4. check_release_assets.py must pass on every file (name + private key scan,
#      nested archives included); any failure aborts before anything is sent
#   5. tag v<Version> must exist locally and on origin at the same commit, and
#      docs\releases\<Version>.md must exist (used as release notes)
#   6. create the release, or upload only the missing assets to an existing one
#      (-Clobber replaces assets whose content differs)
#   7. read the release back and compare every asset digest with the local file
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$ReleasesRoot = $env:RD_RELEASES_ROOT,
    [string]$NotesFile,
    [string]$Repo = 'dty2095485/rustdesk-ssh-vless',
    [switch]$Clobber,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$PublishPlatforms = @('windows', 'android')
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (!$ReleasesRoot) { $ReleasesRoot = 'D:\RD\releases' }
if (!$NotesFile) { $NotesFile = Join-Path $repoRoot "docs\releases\$Version.md" }
$python = 'C:\Program Files\Python312\python.exe'
if (!(Test-Path $python)) { $python = 'python' }
$tag = "v$Version"

function Fail([string]$m) { Write-Host "PUBLISH REFUSED: $m"; exit 1 }
# Native tools write progress to stderr; under 'Stop' Windows PowerShell would
# turn that into an error, so run them with 'Continue' and judge the exit code.
function Run([string]$exe, [string[]]$argv) {
    $ErrorActionPreference = 'Continue'
    $out = & $exe @argv 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    return @{ Code = $code; Out = $out }
}
function Sha256([string]$path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower() }

Write-Host "== publish $tag to $Repo$(if ($DryRun) { ' (dry run)' })"

# ---- 1-2. manifest and files -------------------------------------------------
$folder = Join-Path $ReleasesRoot $Version
$manifestPath = Join-Path $folder 'manifest.json'
if (!(Test-Path -LiteralPath $manifestPath)) { Fail "missing $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.version -ne $Version) { Fail "manifest version '$($manifest.version)' is not $Version" }

$assets = @()
foreach ($prop in $manifest.artifacts.PSObject.Properties) {
    $platform = $prop.Name; $entry = $prop.Value
    if ($PublishPlatforms -notcontains $platform) {
        Write-Host "  skip    $platform  $($entry.file)  (never published)"
        continue
    }
    $path = Join-Path $folder $entry.file
    if (!(Test-Path -LiteralPath $path)) { Fail "missing artifact $path" }
    $digest = Sha256 $path
    if ($digest -ne $entry.sha256.ToLower()) { Fail "$($entry.file): sha256 $digest does not match the manifest" }
    $assets += [pscustomobject]@{ Path = $path; Name = (Split-Path $path -Leaf); Sha = $digest; Rel = $entry.file }
    Write-Host "  publish $platform  $($entry.file)"
}
if ($assets.Count -eq 0) { Fail 'no client artifact to publish' }

# ---- 3. SHA256SUMS for exactly the published files ---------------------------
$stage = Join-Path ([IO.Path]::GetTempPath()) "rd-publish-$Version"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$sums = Join-Path $stage 'SHA256SUMS.txt'
$lines = $assets | Sort-Object Rel | ForEach-Object { "$($_.Sha)  $($_.Rel)" }
[IO.File]::WriteAllText($sums, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
$assets += [pscustomobject]@{ Path = $sums; Name = 'SHA256SUMS.txt'; Sha = (Sha256 $sums); Rel = 'SHA256SUMS.txt' }

# ---- 4. private key / server image check -------------------------------------
Write-Host '== check_release_assets.py'
$check = Run $python (@((Join-Path $PSScriptRoot 'check_release_assets.py')) + @($assets | ForEach-Object { $_.Path }))
$check.Out | ForEach-Object { Write-Host "  $_" }
if ($check.Code -ne 0) { Fail 'asset check failed; nothing was uploaded' }

# ---- 5. tag and notes ---------------------------------------------------------
if (!(Test-Path -LiteralPath $NotesFile)) { Fail "missing release notes $NotesFile" }
$local = Run 'git' @('-C', $repoRoot, 'rev-parse', "$tag^{commit}")
if ($local.Code -ne 0) { Fail "tag $tag not found locally" }
$remote = Run 'git' @('-C', $repoRoot, 'ls-remote', 'origin', "refs/tags/$tag^{}", "refs/tags/$tag")
$remoteLine = @($remote.Out | Where-Object { $_ -match "refs/tags/$([regex]::Escape($tag))\^\{\}$" }) + @($remote.Out | Where-Object { $_ -match "refs/tags/$([regex]::Escape($tag))$" })
if (!$remoteLine) { Fail "tag $tag is not on origin; push it first" }
$remoteSha = ($remoteLine[0] -split '\s+')[0]
if ($remoteSha -ne ($local.Out | Select-Object -Last 1)) { Fail "tag $tag on origin ($remoteSha) differs from local" }
Write-Host "  tag $tag = $remoteSha (local = origin)"

# ---- 6. create or update -------------------------------------------------------
# jq filter without double quotes: Windows PowerShell mangles quotes in native args
$view = Run 'gh' @('release', 'view', $tag, '--repo', $Repo, '--json', 'assets', '-q', '.assets[] | [.name, .digest] | @tsv')
if ($view.Code -ne 0 -and -not ($view.Out -match 'release not found')) {
    $view.Out | ForEach-Object { Write-Host "  $_" }
    Fail 'could not query GitHub for an existing release'
}
$existing = @{}
if ($view.Code -eq 0) {
    foreach ($l in $view.Out) { $p = "$l" -split "`t"; if ($p[0]) { $existing[$p[0]] = ("$($p[1])" -replace '^sha256:', '') } }
    $todo = @(); $replace = @()
    foreach ($a in $assets) {
        if (!$existing.ContainsKey($a.Name)) { $todo += $a }
        elseif ($existing[$a.Name] -and $existing[$a.Name] -ne $a.Sha) { $replace += $a }
    }
    foreach ($a in $replace) { Write-Host "  differs on GitHub: $($a.Name)" }
    if ($replace.Count -and !$Clobber) { Fail 'release assets differ from the local files; re-run with -Clobber to replace them' }
    $send = @($todo + $replace)
    Write-Host "== release $tag exists: $($send.Count) asset(s) to upload"
    if ($send.Count -and !$DryRun) {
        $argv = @('release', 'upload', $tag, '--repo', $Repo) + @($send | ForEach-Object { $_.Path })
        if ($Clobber) { $argv += '--clobber' }
        $r = Run 'gh' $argv; $r.Out | ForEach-Object { Write-Host "  $_" }
        if ($r.Code -ne 0) { Fail "gh release upload failed (exit $($r.Code))" }
    }
} else {
    Write-Host "== create release $tag with $($assets.Count) asset(s)"
    if (!$DryRun) {
        $argv = @('release', 'create', $tag, '--repo', $Repo, '--verify-tag', '--title', $Version, '--notes-file', $NotesFile) + @($assets | ForEach-Object { $_.Path })
        $r = Run 'gh' $argv; $r.Out | ForEach-Object { Write-Host "  $_" }
        if ($r.Code -ne 0) { Fail "gh release create failed (exit $($r.Code))" }
    }
}
if ($DryRun) { Write-Host 'DRY RUN: nothing was uploaded'; exit 0 }

# ---- 7. read back ----------------------------------------------------------------
$view = Run 'gh' @('release', 'view', $tag, '--repo', $Repo, '--json', 'assets,url', '-q', '.url, (.assets[] | [.name, .digest] | @tsv)')
if ($view.Code -ne 0) { Fail 'could not read the release back' }
$url = $view.Out | Select-Object -First 1
$remoteAssets = @{}
foreach ($l in ($view.Out | Select-Object -Skip 1)) { $p = "$l" -split "`t"; $remoteAssets[$p[0]] = ("$($p[1])" -replace '^sha256:', '') }
$bad = 0
foreach ($a in $assets) {
    $d = $remoteAssets[$a.Name]
    if (!$d) { Write-Host "  MISSING on GitHub: $($a.Name)"; $bad++ }
    elseif ($d -ne $a.Sha) { Write-Host "  DIGEST MISMATCH: $($a.Name)"; $bad++ }
    else { Write-Host "  ok  $($a.Name)  $d" }
}
foreach ($n in $remoteAssets.Keys) {
    if (!($assets | Where-Object { $_.Name -eq $n })) { Write-Host "  note: extra asset on GitHub not from this run: $n" }
}
if ($bad) { Fail "$bad asset(s) did not verify after upload" }
Write-Host "PUBLISHED: $url"
