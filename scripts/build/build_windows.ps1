# Compile the Windows payload (Rust binaries, Flutter core DLL, virtual-display
# DLL, Flutter runner bundle) from a tagged worktree.
param(
    [Parameter(Mandatory = $true)][string]$Worktree,
    [string]$BuildName,
    [string]$BuildNumber,
    [string]$Log
)
$ErrorActionPreference = 'Continue'

$worktreePath = (Resolve-Path -LiteralPath $Worktree).Path
$client = Join-Path $worktreePath 'client'
if (!$BuildName -or !$BuildNumber) {
    $tag = (& git -C $worktreePath describe --tags --exact-match 2>$null)
    if (!$tag -or !$tag.StartsWith('v')) { throw "worktree is not at a release tag: '$tag'" }
    $parts = $tag.Substring(1).Split('.')
    if (!$BuildName) { $BuildName = ($parts[0..2] -join '.') }
    if (!$BuildNumber) { $BuildNumber = $parts[3] }
}
if (!$Log) { $Log = Join-Path $env:TEMP "rustdesk-build-$BuildName.$BuildNumber.log" }
New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
'' | Set-Content -Path $Log
function Log([string]$m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"
    Write-Host $line
    Add-Content -Path $Log -Value $line
}

Write-Host "== preflight =="
$tag = (& git -C $worktreePath describe --tags --exact-match 2>$null)
$dirty = (& git -C $worktreePath status --porcelain 2>$null)
if ($dirty) { Write-Host 'PREFLIGHT FAILED: worktree is dirty'; exit 1 }
Write-Host "  worktree         $worktreePath"
Write-Host "  tag              $tag"
Write-Host "  build            $BuildName+$BuildNumber"

$vcvars = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
if (!(Test-Path $vcvars)) { Write-Host "PREFLIGHT FAILED: vcvars missing: $vcvars"; exit 1 }
foreach ($line in (cmd /c "`"$vcvars`" >nul 2>&1 && set")) {
    if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
$env:VCPKG_ROOT = if ($env:VCPKG_ROOT -and (Test-Path (Join-Path $env:VCPKG_ROOT 'installed'))) { $env:VCPKG_ROOT } else { 'D:\RD\tools\vcpkg' }
$env:VCPKG_DEFAULT_TRIPLET = 'x64-windows-static'
$env:VSLANG = '1033'
$env:PATH = "D:\RD\tools\flutter-sdk\bin;" + $env:PATH
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'
Log "VCPKG_ROOT=$env:VCPKG_ROOT"

Push-Location $client
try {
    Log '== cargo build (bins: inline,vram,hwcodec) =='
    & cargo build --release --features inline,vram,hwcodec --bins *>&1 | Select-Object -Last 6 | ForEach-Object { Log $_ }
    Log "bins_exit=$LASTEXITCODE"

    Log '== cargo build (lib: flutter,inline,vram,hwcodec) =='
    & cargo build --release --lib --features flutter,inline,vram,hwcodec *>&1 | Select-Object -Last 6 | ForEach-Object { Log $_ }
    Log "lib_exit=$LASTEXITCODE"

    Log '== cargo build (-p dylib_virtual_display) =='
    & cargo build --release -p dylib_virtual_display *>&1 | Select-Object -Last 4 | ForEach-Object { Log $_ }
    Log "vdisplay_exit=$LASTEXITCODE"

    foreach ($f in @('target\release\librustdesk.dll', 'target\release\dylib_virtual_display.dll')) {
        if (!(Test-Path (Join-Path $client $f))) { Log "STOP: $f missing"; exit 1 }
    }

    Log "== flutter build windows ($BuildName+$BuildNumber) =="
    Push-Location (Join-Path $client 'flutter')
    try {
        & flutter build windows --release --build-name $BuildName --build-number $BuildNumber *>&1 | Select-Object -Last 6 | ForEach-Object { Log $_ }
        Log "flutter_exit=$LASTEXITCODE"
    } finally { Pop-Location }

    $exe = Join-Path $client 'flutter\build\windows\x64\runner\Release\rustdesk.exe'
    if (!(Test-Path $exe)) { Log 'STOP: flutter runner exe missing'; exit 1 }
    $v = (Get-Item $exe).VersionInfo
    Log ("runner version=" + ("{0}.{1}.{2}.{3}" -f $v.FileMajorPart, $v.FileMinorPart, $v.FileBuildPart, $v.FilePrivatePart))
} finally {
    Pop-Location
}
Log 'WINDOWS_BUILD_DONE'
