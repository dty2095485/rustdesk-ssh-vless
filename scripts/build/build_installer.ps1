# Build the single-file Windows installer from a tagged worktree.
#
# Everything is taken from the worktree (client source + installer assets), so a
# build is reproducible from the tag alone. The script refuses to run unless the
# worktree is exactly at tag v<ReleaseVersion> and is clean.
param(
    [Parameter(Mandatory = $true)][string]$Worktree,
    [Parameter(Mandatory = $true)][string]$ReleaseVersion,
    [string]$ReleasesRoot = $env:RD_RELEASES_ROOT,
    [string]$OutDir,
    [switch]$VerifyOnly,
    [switch]$KeepExistingNetworkProfiles
)
$ErrorActionPreference = 'Stop'

$scriptsDir = $PSScriptRoot
$worktreePath = (Resolve-Path -LiteralPath $Worktree).Path
$client = Join-Path $worktreePath 'client'
$installerAssets = Join-Path $worktreePath 'installer'
$python = 'C:\Program Files\Python312\python.exe'
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (!$ReleasesRoot) { $ReleasesRoot = 'D:\RD\releases' }
$archiveDir = Join-Path $ReleasesRoot 'windows\ssh'
if (!$OutDir) { $OutDir = Join-Path $ReleasesRoot '.build-output' }
$out = Join-Path $OutDir "rustdesk-$ReleaseVersion-x86_64.exe"

function Fail([string]$message) {
    Write-Host "PREFLIGHT FAILED: $message"
    exit 1
}
function Info([string]$message) { Write-Host "  $message" }

Write-Host "== preflight =="
if (!(Test-Path -LiteralPath (Join-Path $client 'Cargo.toml'))) { Fail "not a client worktree: $client" }
if (!(Test-Path -LiteralPath (Join-Path $installerAssets 'bootstrap.cs'))) { Fail "installer assets missing in worktree: $installerAssets" }

$tag = (& git -C $worktreePath describe --tags --exact-match 2>$null)
if ($tag -ne "v$ReleaseVersion") { Fail "worktree tag is '$tag', expected 'v$ReleaseVersion'" }
Info "tag              v$ReleaseVersion"
$dirty = (& git -C $worktreePath status --porcelain 2>$null)
if ($dirty) { Fail "worktree is dirty; build from a clean tag worktree" }
Info "worktree clean   yes"

$officialVersion = ($ReleaseVersion -split '\.')[0..2] -join '.'
$cargoLine = Select-String -LiteralPath (Join-Path $client 'Cargo.toml') -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (!$cargoLine) { Fail 'Cargo.toml has no version line' }
$cargoVersion = $cargoLine.Matches[0].Groups[1].Value
if ($cargoVersion -ne $officialVersion) { Fail "Cargo.toml version '$cargoVersion' != official '$officialVersion'" }
Info "Cargo.toml       $cargoVersion (official)"

$flutterRelease = Join-Path $client 'flutter\build\windows\x64\runner\Release'
$coreDll = Join-Path $client 'target\release\librustdesk.dll'
$displayDll = Join-Path $client 'target\release\dylib_virtual_display.dll'
$payloadReady = (Test-Path -LiteralPath (Join-Path $flutterRelease 'rustdesk.exe')) -and (Test-Path -LiteralPath $coreDll) -and (Test-Path -LiteralPath $displayDll)
Info "payload built    $(if ($payloadReady) { 'yes' } else { 'no (run scripts\build\build-windows.ps1 first)' })"

if (!(Test-Path -LiteralPath $csc)) { Fail "csc.exe not found: $csc" }
if (!(Test-Path -LiteralPath $python)) { Fail "python not found: $python" }
Info "toolchain        csc + python present"

if ($VerifyOnly) {
    Write-Host 'PREFLIGHT OK'
    exit 0
}
if (!$payloadReady) { Fail "payload not built in $client" }

$exeVersion = (Get-Item -LiteralPath (Join-Path $flutterRelease 'rustdesk.exe')).VersionInfo
$numericVersion = "$($exeVersion.FileMajorPart).$($exeVersion.FileMinorPart).$($exeVersion.FileBuildPart).$($exeVersion.FilePrivatePart)"
if ($numericVersion -ne $ReleaseVersion) { Fail "client EXE version $numericVersion differs from requested $ReleaseVersion" }

$build = Join-Path $client 'build\installer'
$staged = Join-Path $build 'RustDesk-client'
$stage = Join-Path $build 'installer-stage'
$zip = Join-Path $build 'payload.zip'
New-Item -ItemType Directory -Force -Path $archiveDir, $OutDir, $build | Out-Null
foreach ($target in @($staged, $stage)) {
    $resolved = [IO.Path]::GetFullPath($target)
    if (!$resolved.StartsWith([IO.Path]::GetFullPath($build) + '\', [StringComparison]::OrdinalIgnoreCase)) {
        Fail "unsafe packaging directory: $resolved"
    }
    if ((Test-Path -LiteralPath $target) -and (Get-Item -LiteralPath $target).LinkType) {
        Fail "refusing to replace linked packaging directory: $target"
    }
}
if ($KeepExistingNetworkProfiles) {
    foreach ($profileName in @('VPS1-network.json', 'VPS3-network.json')) {
        if (!(Test-Path -LiteralPath (Join-Path $archiveDir $profileName) -PathType Leaf)) {
            Fail "required existing network profile is missing: $profileName"
        }
    }
}

Write-Host '== assemble payload =='
if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged -Recurse -Force }
New-Item -ItemType Directory -Path $staged | Out-Null
Copy-Item -Path (Join-Path $flutterRelease '*') -Destination $staged -Recurse -Force
Copy-Item -LiteralPath $coreDll -Destination (Join-Path $staged 'librustdesk.dll') -Force
Copy-Item -LiteralPath $displayDll -Destination (Join-Path $staged 'dylib_virtual_display.dll') -Force
& (Join-Path $scriptsDir 'prepare_xray.ps1') -OutputDirectory $staged
if (!$?) { Fail 'prepare_xray.ps1 failed' }
& $python (Join-Path $scriptsDir 'verify_windows_release.py') $staged $ReleaseVersion
if ($LASTEXITCODE -ne 0) { Fail 'Windows payload version/privacy verification failed' }

if (Test-Path -LiteralPath $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item (Join-Path $staged '*') $stage -Recurse -Force
if (Test-Path -LiteralPath $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force

Write-Host '== package installer =='
if (Test-Path -LiteralPath $out) { Remove-Item $out -Force }
& $csc /nologo /target:winexe /optimize+ /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll `
    "/win32manifest:$(Join-Path $installerAssets 'setup.manifest')" "/resource:$zip,payload.zip" "/out:$out" `
    (Join-Path $installerAssets 'bootstrap.cs')
if ($LASTEXITCODE -ne 0) { Fail "csc failed: $LASTEXITCODE" }

if (!$KeepExistingNetworkProfiles) {
    & $python (Join-Path $scriptsDir 'export_network_profiles.py') --output-dir $archiveDir --basename ([IO.Path]::GetFileNameWithoutExtension($out))
    if ($LASTEXITCODE -ne 0) { Fail 'network JSON generation failed' }
}

$registeredJson = & $python (Join-Path $scriptsDir 'manage_versions.py') register --root $ReleasesRoot --version $ReleaseVersion --artifact $out --platform windows --internal-version $ReleaseVersion --note 'Windows x64 Flutter installer; TLS/REALITY/SSH; no private network defaults'
if ($LASTEXITCODE -ne 0) { Fail 'version registration failed' }
$registered = $registeredJson | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $out).Hash -ne (Get-FileHash -LiteralPath $registered.artifact).Hash) { Fail 'archived installer hash mismatch' }
Remove-Item -LiteralPath $out
Write-Host "INSTALLER BUILT: $($registered.artifact)"
