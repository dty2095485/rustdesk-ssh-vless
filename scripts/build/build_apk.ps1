# Build the Android arm64-v8a APK from a tagged worktree.
#
# The Rust core must already be cross-compiled into
# <client>\flutter\android\app\src\main\jniLibs\arm64-v8a (see
# scripts/build/build_android_core.sh, runs in WSL). This script only does the
# Flutter/Gradle half.
param(
    [Parameter(Mandatory = $true)][string]$Worktree,
    [string]$ReleaseVersion,
    [string]$ReleasesRoot = $env:RD_RELEASES_ROOT,
    [string]$OutDir,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'

$scriptsDir = $PSScriptRoot
$worktreePath = (Resolve-Path -LiteralPath $Worktree).Path
$client = Join-Path $worktreePath 'client'
$flutterDir = Join-Path $client 'flutter'
$jni = Join-Path $flutterDir 'android\app\src\main\jniLibs\arm64-v8a'
$appGradle = Join-Path $flutterDir 'android\app\build.gradle'
$gradleProps = Join-Path $flutterDir 'android\gradle.properties'
$python = 'C:\Program Files\Python312\python.exe'
if (!$ReleasesRoot) { $ReleasesRoot = 'D:\RD\releases' }
if (!$OutDir) { $OutDir = Join-Path $ReleasesRoot '.build-output' }

function Fail([string]$message) {
    Write-Host "PREFLIGHT FAILED: $message"
    exit 1
}

Write-Host '== preflight =='
if (!(Test-Path -LiteralPath (Join-Path $client 'Cargo.toml'))) { Fail "not a client worktree: $client" }
$tag = (& git -C $worktreePath describe --tags --exact-match 2>$null)
if (!$tag -or !$tag.StartsWith('v')) { Fail "worktree is not at a release tag (got '$tag')" }
if (!$ReleaseVersion) { $ReleaseVersion = $tag.Substring(1) }
if ($tag -ne "v$ReleaseVersion") { Fail "worktree tag is '$tag', expected 'v$ReleaseVersion'" }
Write-Host "  tag              v$ReleaseVersion"
$dirty = (& git -C $worktreePath status --porcelain 2>$null)
if ($dirty) { Fail 'worktree is dirty; build from a clean tag worktree' }
Write-Host '  worktree clean   yes'

foreach ($lib in @('librustdesk.so', 'libc++_shared.so', 'libxray.so')) {
    if (!(Test-Path -LiteralPath (Join-Path $jni $lib))) {
        Fail "missing $lib in jniLibs (run scripts/build/build_android_core.sh and place libxray.so)"
    }
}
Write-Host '  native libs      librustdesk.so + libc++_shared.so + libxray.so'

if ($VerifyOnly) {
    Write-Host 'PREFLIGHT OK'
    exit 0
}

$env:ANDROID_HOME = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { 'D:\RD\tools\android-sdk' }
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:JAVA_HOME = (Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory | Select-Object -First 1).FullName
$env:PATH = "$env:JAVA_HOME\bin;D:\RD\tools\flutter-sdk\bin;" + $env:PATH
$env:FLUTTER_SUPPRESS_ANALYTICS = 'true'

$buildCode = 2068
$catalog = Join-Path $ReleasesRoot 'versions-index.json'
if (Test-Path -LiteralPath $catalog) {
    $index = Get-Content -LiteralPath $catalog -Raw | ConvertFrom-Json
    foreach ($entry in $index.versions) {
        foreach ($artifact in $entry.artifacts.PSObject.Properties.Value) {
            if ($artifact.build_code -ge $buildCode) { $buildCode = [int]$artifact.build_code + 1 }
        }
    }
}
$out = Join-Path $OutDir "rustdesk-$ReleaseVersion-aarch64.apk"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# Same two temporary edits official CI applies for an unsigned build: use the
# debug signing config and give Gradle more heap. Both are reverted below; the
# files contain non-ASCII text, so the patch goes through .NET with explicit
# UTF-8 and no BOM.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$gradleBackup = "$appGradle.bak"
$propsBackup = "$gradleProps.bak"
Copy-Item -LiteralPath $appGradle -Destination $gradleBackup -Force
Copy-Item -LiteralPath $gradleProps -Destination $propsBackup -Force
try {
    $text = [System.IO.File]::ReadAllText($appGradle)
    [System.IO.File]::WriteAllText($appGradle, $text.Replace('signingConfigs.release', 'signingConfigs.debug'), $utf8NoBom)
    $text = [System.IO.File]::ReadAllText($gradleProps)
    [System.IO.File]::WriteAllText($gradleProps, $text.Replace('org.gradle.jvmargs=-Xmx1024M', 'org.gradle.jvmargs=-Xmx2g'), $utf8NoBom)

    Push-Location $flutterDir
    try {
        & flutter build apk --release --target-platform android-arm64 --split-per-abi --build-name $ReleaseVersion --build-number $buildCode
        if ($LASTEXITCODE -ne 0) { Fail "flutter build apk failed ($LASTEXITCODE)" }
    } finally {
        Pop-Location
    }

    $built = Join-Path $flutterDir 'build\app\outputs\flutter-apk\app-arm64-v8a-release.apk'
    if (!(Test-Path -LiteralPath $built)) { Fail "APK not found at $built" }
    Copy-Item -LiteralPath $built -Destination $out -Force
} finally {
    Move-Item -LiteralPath $gradleBackup -Destination $appGradle -Force
    Move-Item -LiteralPath $propsBackup -Destination $gradleProps -Force
}

& $python (Join-Path $scriptsDir 'verify_android_release.py') $out $client
if ($LASTEXITCODE -ne 0) { Fail 'APK native-core/privacy verification failed' }
& "$env:ANDROID_HOME\build-tools\34.0.0\apksigner.bat" verify $out
if ($LASTEXITCODE -ne 0) { Fail 'APK signature verification failed' }
$badging = & "$env:ANDROID_HOME\build-tools\34.0.0\aapt.exe" dump badging $out
if ($LASTEXITCODE -ne 0) { Fail 'APK manifest verification failed' }
$packageLine = $badging | Where-Object { $_ -match '^package:' } | Select-Object -First 1
if ($packageLine -notmatch "versionCode='(\d+)'") { Fail 'missing APK versionCode' }
$actualBuildCode = [int]$Matches[1]
if ($packageLine -notmatch "versionName='([^']+)'") { Fail 'missing APK versionName' }
if ($Matches[1] -ne $ReleaseVersion) { Fail "APK versionName $($Matches[1]) != $ReleaseVersion" }

$registeredJson = & $python (Join-Path $scriptsDir 'manage_versions.py') register --root $ReleasesRoot --version $ReleaseVersion --artifact $out --platform android --internal-version $ReleaseVersion --build-code $actualBuildCode --note 'Android arm64-v8a APK; TLS/REALITY/SSH; no private network defaults'
if ($LASTEXITCODE -ne 0) { Fail 'version registration failed' }
$registered = $registeredJson | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $out).Hash -ne (Get-FileHash -LiteralPath $registered.artifact).Hash) { Fail 'archived APK hash mismatch' }
Remove-Item -LiteralPath $out
Write-Host "APK BUILT: $($registered.artifact) (versionName=$ReleaseVersion versionCode=$actualBuildCode)"
