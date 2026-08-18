# Build the self-extracting client exe using RustDesk's own official packer
# (libs/portable/rustdesk-portable-packer), the same tool upstream CI uses --
# not the hand-rolled csc.exe/bootstrap.cs stub in build_installer.ps1, which
# turned out to get blocked by Windows Smart App Control on some machines
# (unsigned + an unusual self-extracting structure it doesn't recognize).
# This produces a native Rust exe instead of a .NET AnyCPU one; it is still
# unsigned, so it does not fix Smart App Control by itself, but it removes
# the "unrecognized packer shape" contribution to that risk.
$ErrorActionPreference = 'Stop'
$root = 'D:\chatgpt\work\rustdesk-ssh'
$repo = "$root\rustdesk"
$release = 'D:\chatgpt\releases\windows\ssh'
$flutterRelease = "$repo\flutter\build\windows\x64\runner\Release"
$coreDll = "$repo\target\release\librustdesk.dll"
$payload = "$repo\rustdesk"
$portable = "$repo\libs\portable"
$manifest = "$repo\res\manifest.xml"
$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$out = "$release\RustDesk-VLESS-Portable-SSH-$stamp.exe"

New-Item -ItemType Directory -Path $release -Force | Out-Null

if (!(Test-Path -LiteralPath "$flutterRelease\rustdesk.exe")) {
    throw "Flutter Windows release was not found: $flutterRelease"
}
if (!(Test-Path -LiteralPath $coreDll)) {
    throw "Flutter-enabled RustDesk core DLL was not found: $coreDll"
}

# Assemble the payload folder the packer will embed (same layout upstream CI uses).
if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
New-Item -ItemType Directory -Path $payload | Out-Null
Copy-Item -Path "$flutterRelease\*" -Destination $payload -Recurse -Force
Copy-Item -LiteralPath $coreDll -Destination "$payload\librustdesk.dll" -Force

# Upstream CI strips this so the packer's own DPI-awareness setting (set in
# libs/portable's own manifest handling) is the one that applies; harmless to
# repeat on an already-stripped manifest.
(Get-Content -LiteralPath $manifest) | Where-Object { $_ -notmatch 'dpiAware' } | Set-Content -LiteralPath $manifest

Push-Location $portable
try {
    if (Test-Path 'data.bin') { Remove-Item 'data.bin' -Force }
    python .\generate.py -f "$payload\" -o . -e "$payload\rustdesk.exe"
    if ($LASTEXITCODE -ne 0) { throw "generate.py failed: $LASTEXITCODE" }
    cargo build --locked --release
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}

$built = "$repo\target\release\rustdesk-portable-packer.exe"
if (!(Test-Path -LiteralPath $built)) { throw "Packer output not found: $built" }
if (Test-Path $out) { Remove-Item $out -Force }
Copy-Item -LiteralPath $built -Destination $out -Force
Get-Item $out | Select-Object Name, Length, LastWriteTime | Format-List
Write-Host "PORTABLE EXE BUILT: $out"
