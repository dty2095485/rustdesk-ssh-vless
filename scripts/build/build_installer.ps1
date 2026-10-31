# Build the Windows installer the way upstream packages it: the self-extracting
# packer in libs/portable (self-contained EXE, brotli-compressed payload, icon and
# version resource compiled by winres), named rustdesk-<version>-x86_64.exe.
#
# Everything comes from the tag worktree, which must be clean and exactly at
# tag v<ReleaseVersion>; the payload must already be compiled in that worktree
# (scripts/build/build_windows.ps1).
param(
    [Parameter(Mandatory = $true)][string]$Worktree,
    [Parameter(Mandatory = $true)][string]$ReleaseVersion,
    [string]$ReleasesRoot = $env:RD_RELEASES_ROOT,
    [string]$OutDir,
    [switch]$VerifyOnly,
    [switch]$KeepExistingNetworkProfiles,
    [int]$CompressionLevel = 11
)
$ErrorActionPreference = 'Stop'

$scriptsDir = $PSScriptRoot
$worktreePath = (Resolve-Path -LiteralPath $Worktree).Path
$client = Join-Path $worktreePath 'client'
$portableDir = Join-Path $client 'libs\portable'
$python = 'C:\Program Files\Python312\python.exe'
if (!$ReleasesRoot) { $ReleasesRoot = 'D:\RD\releases' }
$archiveDir = Join-Path $ReleasesRoot 'windows\ssh'
if (!$OutDir) { $OutDir = Join-Path $ReleasesRoot '.build-output' }
$out = Join-Path $OutDir "rustdesk-$ReleaseVersion-x86_64.exe"

function Fail([string]$message) {
    Write-Host "PREFLIGHT FAILED: $message"
    exit 1
}
function Info([string]$message) { Write-Host "  $message" }

Write-Host '== preflight =='
if (!(Test-Path -LiteralPath (Join-Path $client 'Cargo.toml'))) { Fail "not a client worktree: $client" }
if (!(Test-Path -LiteralPath (Join-Path $portableDir 'generate.py'))) { Fail "official packer missing: $portableDir" }

$tag = (& git -C $worktreePath describe --tags --exact-match 2>$null)
if ($tag -ne "v$ReleaseVersion") { Fail "worktree tag is '$tag', expected 'v$ReleaseVersion'" }
Info "tag              v$ReleaseVersion"
$dirty = (& git -C $worktreePath status --porcelain 2>$null)
if ($dirty) { Fail 'worktree is dirty; build from a clean tag worktree' }
Info 'worktree clean   yes'

$officialVersion = ($ReleaseVersion -split '\.')[0..2] -join '.'
$cargoLine = Select-String -LiteralPath (Join-Path $client 'Cargo.toml') -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (!$cargoLine) { Fail 'Cargo.toml has no version line' }
$cargoVersion = $cargoLine.Matches[0].Groups[1].Value
if ($cargoVersion -ne $officialVersion) { Fail "Cargo.toml version '$cargoVersion' != official '$officialVersion'" }
Info "Cargo.toml       $cargoVersion (official)"

$flutterRelease = Join-Path $client 'flutter\build\windows\x64\runner\Release'
$coreDll = Join-Path $client 'target\release\librustdesk.dll'
$displayDll = Join-Path $client 'target\release\dylib_virtual_display.dll'
$payloadReady = (Test-Path -LiteralPath (Join-Path $flutterRelease 'rustdesk.exe')) -and
    (Test-Path -LiteralPath $coreDll) -and (Test-Path -LiteralPath $displayDll)
Info "payload built    $(if ($payloadReady) { 'yes' } else { 'no (run scripts\build\build_windows.ps1 first)' })"
if (!(Test-Path -LiteralPath $python)) { Fail "python not found: $python" }
& $python -c 'import brotli' 2>$null
if ($LASTEXITCODE -ne 0) { Fail 'python module brotli is required (pip install brotli)' }
Info 'toolchain        python + brotli present'

if ($VerifyOnly) {
    Write-Host 'PREFLIGHT OK'
    exit 0
}
if (!$payloadReady) { Fail "payload not built in $client" }

$exeVersion = (Get-Item -LiteralPath (Join-Path $flutterRelease 'rustdesk.exe')).VersionInfo
$numericVersion = "$($exeVersion.FileMajorPart).$($exeVersion.FileMinorPart).$($exeVersion.FileBuildPart).$($exeVersion.FilePrivatePart)"
if ($numericVersion -ne $ReleaseVersion) { Fail "client EXE version $numericVersion differs from requested $ReleaseVersion" }

$build = Join-Path $client 'build\installer'
$payload = Join-Path $build 'rustdesk'
New-Item -ItemType Directory -Force -Path $archiveDir, $OutDir, $build | Out-Null
if (![IO.Path]::GetFullPath($payload).StartsWith([IO.Path]::GetFullPath($build) + '\', [StringComparison]::OrdinalIgnoreCase)) {
    Fail "unsafe payload directory: $payload"
}
if ((Test-Path -LiteralPath $payload) -and (Get-Item -LiteralPath $payload).LinkType) {
    Fail "refusing to replace linked payload directory: $payload"
}

Write-Host '== assemble payload =='
if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
New-Item -ItemType Directory -Path $payload | Out-Null
Copy-Item -Path (Join-Path $flutterRelease '*') -Destination $payload -Recurse -Force
Copy-Item -LiteralPath $coreDll -Destination (Join-Path $payload 'librustdesk.dll') -Force
Copy-Item -LiteralPath $displayDll -Destination (Join-Path $payload 'dylib_virtual_display.dll') -Force
& (Join-Path $scriptsDir 'prepare_xray.ps1') -OutputDirectory $payload
if (!$?) { Fail 'prepare_xray.ps1 failed' }
& $python (Join-Path $scriptsDir 'verify_windows_release.py') $payload $ReleaseVersion
if ($LASTEXITCODE -ne 0) { Fail 'Windows payload version/privacy verification failed' }

# Upstream strips the dpiAware element before embedding the manifest into the
# packer; keep that and restore the file afterwards so the worktree stays clean.
$manifestPath = Join-Path $client 'res\manifest.xml'
$manifestBackup = Join-Path $build 'manifest.xml.bak'
Copy-Item -LiteralPath $manifestPath -Destination $manifestBackup -Force
try {
    $manifestText = [IO.File]::ReadAllText($manifestPath)
    [IO.File]::WriteAllText($manifestPath, ($manifestText -split "`r?`n" | Where-Object { $_ -notmatch 'dpiAware' }) -join "`n")

    Write-Host '== generate package metadata and build the packer =='
    $env:RUSTDESK_PACKER_VERSION = $ReleaseVersion
    Push-Location $portableDir
    try {
        & $python 'generate.py' -f $payload -o $portableDir -e (Join-Path $payload 'rustdesk.exe') -l $CompressionLevel
        if ($LASTEXITCODE -ne 0) { Fail "generate.py failed: $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
    # cargo writes to the workspace target dir when the crate is a workspace
    # member, and to its own target dir when built standalone; accept both.
    $packer = @(
        (Join-Path $portableDir 'target\release\rustdesk-portable-packer.exe'),
        (Join-Path $client 'target\release\rustdesk-portable-packer.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (!$packer) { Fail 'packer not produced (checked crate and workspace target dirs)' }
    if (Test-Path -LiteralPath $out) { Remove-Item $out -Force }
    Copy-Item -LiteralPath $packer -Destination $out -Force
} finally {
    Move-Item -LiteralPath $manifestBackup -Destination $manifestPath -Force
    Remove-Item Env:\RUSTDESK_PACKER_VERSION -ErrorAction SilentlyContinue
}

Write-Host '== verify installer =='
& $python (Join-Path $scriptsDir 'check_installer_resources.py') $out
if ($LASTEXITCODE -ne 0) { Fail 'installer is missing its icon, version or manifest resource' }
$installerVersion = (Get-Item -LiteralPath $out).VersionInfo
$installerNumeric = "$($installerVersion.FileMajorPart).$($installerVersion.FileMinorPart).$($installerVersion.FileBuildPart).$($installerVersion.FilePrivatePart)"
# The packer's version resource comes from winres/the crate version, so it
# reports the upstream version (1.5.1); the fork revision lives in the file
# name, manifest and SHA256SUMS, exactly like the upstream assets.
if ((($installerNumeric -split '\.')[0..2] -join '.') -ne $officialVersion) { Fail "installer file version $installerNumeric != upstream $officialVersion" }
Info "installer        $installerNumeric, $(('{0:N0}' -f (Get-Item $out).Length)) B"

if (!$KeepExistingNetworkProfiles) {
    & $python (Join-Path $scriptsDir 'export_network_profiles.py') --output-dir $archiveDir --basename ([IO.Path]::GetFileNameWithoutExtension($out))
    if ($LASTEXITCODE -ne 0) { Fail 'network JSON generation failed' }
}

$registeredJson = & $python (Join-Path $scriptsDir 'manage_versions.py') register --root $ReleasesRoot --version $ReleaseVersion --artifact $out --platform windows --internal-version $ReleaseVersion --note 'Windows x64 self-extracting installer (upstream libs/portable packer); TLS/REALITY/SSH; no private network defaults'
if ($LASTEXITCODE -ne 0) { Fail 'version registration failed' }
$registered = $registeredJson | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $out).Hash -ne (Get-FileHash -LiteralPath $registered.artifact).Hash) { Fail 'archived installer hash mismatch' }
Remove-Item -LiteralPath $out
Write-Host "INSTALLER BUILT: $($registered.artifact)"
