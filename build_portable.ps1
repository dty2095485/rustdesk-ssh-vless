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
