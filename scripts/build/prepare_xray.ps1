param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$CacheDir = $env:RD_XRAY_CACHE
)

$ErrorActionPreference = 'Stop'
$cache = if ($CacheDir) { $CacheDir } else { 'D:\RD\work\rustdesk-ssh\xray-cache' }
$version = 'v26.9.8'
$archive = "$cache\Xray-windows-64-$version.zip"
$extract = "$cache\Xray-windows-64-$version"
$expectedSha256 = 'FFB3DC91680A819F021C1A94FC1A726DA6C7081801191BC5D40CC8F225503D46'
$url = "https://github.com/XTLS/Xray-core/releases/download/$version/Xray-windows-64.zip"

New-Item -ItemType Directory -Path $cache -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

if (!(Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri $url -OutFile $archive
}

$actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($actualSha256 -ne $expectedSha256) {
    throw "Xray archive SHA256 mismatch: expected $expectedSha256, got $actualSha256"
}

if (Test-Path -LiteralPath $extract) {
    Remove-Item -LiteralPath $extract -Recurse -Force
}
Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force

$xray = "$extract\xray.exe"
if (!(Test-Path -LiteralPath $xray)) {
    throw "The verified Xray archive does not contain xray.exe"
}
Copy-Item -LiteralPath $xray -Destination "$OutputDirectory\xray.exe" -Force

$license = "$extract\LICENSE"
if (Test-Path -LiteralPath $license) {
    Copy-Item -LiteralPath $license -Destination "$OutputDirectory\xray-LICENSE.txt" -Force
}

Write-Host "XRAY SIDECAR READY: $OutputDirectory\xray.exe ($version)"
