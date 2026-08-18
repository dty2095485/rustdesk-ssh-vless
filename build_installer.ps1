# Build a single-exe installer for the SSH-enabled client.
# Inputs and temporary packaging artifacts live with the active source; only
# finished setup EXEs are written to the central release directory.
$ErrorActionPreference = 'Stop'
$root = 'D:\chatgpt\work\rustdesk-ssh'
$repo = "$root\rustdesk"
$release = 'D:\chatgpt\releases\windows\ssh'
$build = "$repo\build\installer"
$installerAssets = "$root\installer"
$flutterRelease = "$repo\flutter\build\windows\x64\runner\Release"
$coreDll = "$repo\target\release\librustdesk.dll"
$client  = "$build\RustDesk-client"
$stage   = "$build\installer-stage"
$zip     = "$build\payload.zip"
$stamp   = Get-Date -Format 'yyyyMMdd-HHmm'
$out     = "$release\RustDesk-VLESS-Setup-SSH-$stamp.exe"
$csc     = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$bootstrap = "$installerAssets\bootstrap.cs"
$manifest  = "$installerAssets\setup.manifest"

New-Item -ItemType Directory -Path $release -Force | Out-Null
New-Item -ItemType Directory -Path $build -Force | Out-Null

if (!(Test-Path -LiteralPath $bootstrap) -or !(Test-Path -LiteralPath $manifest)) {
    throw "Installer assets were not found in: $installerAssets"
}

if (!(Test-Path -LiteralPath "$flutterRelease\rustdesk.exe")) {
    throw "Flutter Windows release was not found: $flutterRelease"
}
if (!(Test-Path -LiteralPath $coreDll)) {
    throw "Flutter-enabled RustDesk core DLL was not found: $coreDll"
}

# Always assemble a coherent payload from the current Flutter build + core DLL.
if (Test-Path -LiteralPath $client) { Remove-Item -LiteralPath $client -Recurse -Force }
New-Item -ItemType Directory -Path $client | Out-Null
Copy-Item -Path "$flutterRelease\*" -Destination $client -Recurse -Force
Copy-Item -LiteralPath $coreDll -Destination "$client\librustdesk.dll" -Force

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item "$client\*" $stage -Recurse -Force

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$stage\*" -DestinationPath $zip -Force

if (Test-Path $out) { Remove-Item $out -Force }
& $csc /nologo /target:winexe /optimize+ /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll "/win32manifest:$manifest" "/resource:$zip,payload.zip" "/out:$out" $bootstrap
if ($LASTEXITCODE -ne 0) { Write-Host "CSC FAILED: $LASTEXITCODE"; exit 1 }
if (Test-Path $out) {
    Get-Item $out | Select-Object Name,Length,LastWriteTime | Format-List
    Write-Host "INSTALLER BUILT: $out"
} else {
    Write-Host 'BUILD FAILED'
}
