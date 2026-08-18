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
$virtualDisplayDll = "$repo\target\release\deps\dylib_virtual_display.dll"
$payload = "$repo\rustdesk"
$portable = "$repo\libs\portable"
$manifest = "$repo\res\manifest.xml"

$versionLine = Select-String -Path "$repo\Cargo.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (!$versionLine) { throw "Could not read version from $repo\Cargo.toml" }
$version = $versionLine.Matches[0].Groups[1].Value
$arch = 'x86_64'
# Official naming is rustdesk-{version}-{arch}.exe; keep that shape with an
# identifying prefix since this is the SSH+VLESS fork, not upstream RustDesk.
$out = "$release\rustdesk-vless-ssh-$version-$arch.exe"

New-Item -ItemType Directory -Path $release -Force | Out-Null

if (!(Test-Path -LiteralPath "$flutterRelease\rustdesk.exe")) {
    throw "Flutter Windows release was not found: $flutterRelease"
}
if (!(Test-Path -LiteralPath $coreDll)) {
    throw "Flutter-enabled RustDesk core DLL was not found: $coreDll"
}
if (!(Test-Path -LiteralPath $virtualDisplayDll)) {
    throw "dylib_virtual_display.dll was not found: $virtualDisplayDll (run: cargo build --release --locked -p dylib_virtual_display)"
}

# Assemble the payload folder the packer will embed (same layout upstream CI uses).
# dylib_virtual_display.dll is a separate workspace member the main `cargo
# build` does not produce as a side effect -- upstream's build.py copies it in
# as its own step (build_flutter_windows), which build_installer.ps1 and an
# earlier version of this script both missed, silently shipping without
# virtual-display support. It's only ~290KB uncompressed, so it is not the
# full explanation for this build coming in smaller than an official release;
# treat that gap as still partly unexplained rather than assuming this fixes it.
if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force }
New-Item -ItemType Directory -Path $payload | Out-Null
Copy-Item -Path "$flutterRelease\*" -Destination $payload -Recurse -Force
Copy-Item -LiteralPath $coreDll -Destination "$payload\librustdesk.dll" -Force
Copy-Item -LiteralPath $virtualDisplayDll -Destination "$payload\dylib_virtual_display.dll" -Force

# Virtual-monitor and remote-printer support: upstream CI downloads these as
# prebuilt, separately-signed Windows drivers (driver signing needs a real
# cert + Microsoft attestation, which a plain cargo/flutter build can't
# produce) rather than building them from this source tree. Comparing our
# build against a real official release (byte-level manifest extracted from
# the self-extracting payload format) is what surfaced these as the actual
# explanation for a size gap, not anything wrong with this fork's own code.
$driverCache = "$root\driver-cache"
New-Item -ItemType Directory -Path $driverCache -Force | Out-Null

# usbmmidd (virtual monitor driver) -- upstream's own script does not publish
# a checksum for this one, so pin the hash of what we verified when this
# step was added; a change here means investigate before trusting it, not a
# routine "checksums differ, re-pin".
$usbmmiddZip = "$driverCache\usbmmidd_v2.zip"
$usbmmiddKnownSha256 = '629B51E9944762BAE73948171C65D09A79595CF4C771A82EBC003FBBA5B24F51'
if (!(Test-Path -LiteralPath $usbmmiddZip)) {
    Invoke-WebRequest -Uri 'https://github.com/rustdesk-org/rdev/releases/download/usbmmidd_v2/usbmmidd_v2.zip' -OutFile $usbmmiddZip
}
$usbmmiddActual = (Get-FileHash -LiteralPath $usbmmiddZip -Algorithm SHA256).Hash
if ($usbmmiddActual -ne $usbmmiddKnownSha256) {
    throw "usbmmidd_v2.zip SHA256 mismatch: expected $usbmmiddKnownSha256, got $usbmmiddActual -- upstream has no published checksum for this file, so do not blindly re-pin; check why it changed first."
}
$usbmmiddExtract = "$driverCache\usbmmidd_v2_extracted"
if (Test-Path -LiteralPath $usbmmiddExtract) { Remove-Item -LiteralPath $usbmmiddExtract -Recurse -Force }
Expand-Archive -LiteralPath $usbmmiddZip -DestinationPath $usbmmiddExtract -Force
Remove-Item -Path "$usbmmiddExtract\usbmmidd_v2\Win32" -Recurse -Force
Remove-Item -Path "$usbmmiddExtract\usbmmidd_v2\deviceinstaller64.exe", "$usbmmiddExtract\usbmmidd_v2\deviceinstaller.exe", "$usbmmiddExtract\usbmmidd_v2\usbmmidd.bat" -Force
Copy-Item -Path "$usbmmiddExtract\usbmmidd_v2" -Destination "$payload\usbmmidd_v2" -Recurse -Force

# Remote-printer driver -- upstream's own script publishes and checks SHA256
# for these two; do the same rather than trusting the download blindly.
$printerDriverZip = "$driverCache\rustdesk_printer_driver_v4-1.4.zip"
$printerAdapterZip = "$driverCache\printer_driver_adapter.zip"
$printerSums = "$driverCache\sha256sums"
if (!(Test-Path -LiteralPath $printerDriverZip)) {
    Invoke-WebRequest -Uri 'https://github.com/rustdesk/hbb_common/releases/download/driver/rustdesk_printer_driver_v4-1.4.zip' -OutFile $printerDriverZip
}
if (!(Test-Path -LiteralPath $printerAdapterZip)) {
    Invoke-WebRequest -Uri 'https://github.com/rustdesk/hbb_common/releases/download/driver/printer_driver_adapter.zip' -OutFile $printerAdapterZip
}
Invoke-WebRequest -Uri 'https://github.com/rustdesk/hbb_common/releases/download/driver/sha256sums' -OutFile $printerSums

$sums = Get-Content -LiteralPath $printerSums
$expectDriver = ($sums | Select-String -Pattern '^([a-fA-F0-9]{64}) \*rustdesk_printer_driver_v4-1\.4\.zip$').Matches.Groups[1].Value
$expectAdapter = ($sums | Select-String -Pattern '^([a-fA-F0-9]{64}) \*printer_driver_adapter\.zip$').Matches.Groups[1].Value
$actualDriver = (Get-FileHash -LiteralPath $printerDriverZip -Algorithm SHA256).Hash
$actualAdapter = (Get-FileHash -LiteralPath $printerAdapterZip -Algorithm SHA256).Hash
if (!$expectDriver -or !$expectAdapter) {
    throw "Could not find expected hashes in sha256sums for the printer driver files"
}
if ($actualDriver -ne $expectDriver) {
    throw "rustdesk_printer_driver_v4-1.4.zip SHA256 mismatch: expected $expectDriver, got $actualDriver"
}
if ($actualAdapter -ne $expectAdapter) {
    throw "printer_driver_adapter.zip SHA256 mismatch: expected $expectAdapter, got $actualAdapter"
}
$printerExtract = "$driverCache\printer_extracted"
$adapterExtract = "$driverCache\adapter_extracted"
if (Test-Path -LiteralPath $printerExtract) { Remove-Item -LiteralPath $printerExtract -Recurse -Force }
if (Test-Path -LiteralPath $adapterExtract) { Remove-Item -LiteralPath $adapterExtract -Recurse -Force }
Expand-Archive -LiteralPath $printerDriverZip -DestinationPath $printerExtract -Force
Expand-Archive -LiteralPath $printerAdapterZip -DestinationPath $adapterExtract -Force
New-Item -ItemType Directory -Path "$payload\drivers" -Force | Out-Null
Copy-Item -Path "$printerExtract\rustdesk_printer_driver_v4-1.4" -Destination "$payload\drivers\RustDeskPrinterDriver" -Recurse -Force
Copy-Item -LiteralPath "$adapterExtract\printer_driver_adapter.dll" -Destination "$payload\printer_driver_adapter.dll" -Force

# res/manifest.xml is shared with the main client build (both build.rs and
# libs/portable/build.rs embed it via winres). Upstream CI strips dpiAware
# from it only for the packer step -- by then the main app is already built
# from the intact version, so this only affects the packer's own manifest.
# Do the same here, but on a backup/restore basis so this script never leaves
# the shared file permanently mutated for whatever builds the main app next.
$manifestBackup = "$manifest.bak"
Copy-Item -LiteralPath $manifest -Destination $manifestBackup -Force
try {
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
} finally {
    Copy-Item -LiteralPath $manifestBackup -Destination $manifest -Force
    Remove-Item -LiteralPath $manifestBackup -Force
}

$built = "$repo\target\release\rustdesk-portable-packer.exe"
if (!(Test-Path -LiteralPath $built)) { throw "Packer output not found: $built" }
if (Test-Path $out) { Remove-Item $out -Force }
Copy-Item -LiteralPath $built -Destination $out -Force
Get-Item $out | Select-Object Name, Length, LastWriteTime | Format-List
Write-Host "PORTABLE EXE BUILT: $out"
