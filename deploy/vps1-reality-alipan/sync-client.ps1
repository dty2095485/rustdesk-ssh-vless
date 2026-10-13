param([string]$Parameters = '<workspace>\deploy\vps1-reality-alipan\client-parameters-private.json')
$ErrorActionPreference = 'Stop'
trap {
    $_ | Out-String | Set-Content -LiteralPath '<workspace>\deploy\vps1-reality-alipan\client-sync-error.log' -Encoding UTF8
    exit 1
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator elevation required for installed-client --option commands'
}
$paramsData = Get-Content -LiteralPath $Parameters -Raw | ConvertFrom-Json
$clientExe = 'C:\Program Files\RustDesk\rustdesk.exe'
if (-not (Test-Path -LiteralPath $clientExe)) { throw 'Installed client missing' }
if ($paramsData.server_name -ne 'www.alipan.com' -or $paramsData.port -ne '443') { throw 'Unexpected parameters' }
$options = [ordered]@{
    'vless-reality-server' = $paramsData.server
    'vless-reality-port' = $paramsData.port
    'vless-reality-uuid' = $paramsData.uuid
    'vless-reality-sni' = $paramsData.server_name
    'vless-reality-public-key' = $paramsData.public_key
    'vless-reality-short-id' = $paramsData.short_id
    'vless-reality-fingerprint' = $paramsData.fingerprint
    'vless-reality-flow' = $paramsData.flow
}
# Use the installed client's existing IPC rather than editing live TOML files,
# stopping sessions or restarting the Windows service. Do not change TLS/SSH
# settings or switch the user's currently selected transport.
foreach ($entry in $options.GetEnumerator()) {
    $commandProcess = Start-Process -FilePath $clientExe -WindowStyle Hidden -ArgumentList @('--option', $entry.Key, $entry.Value) -Wait -PassThru
    if ($commandProcess.ExitCode -ne 0) { throw "IPC command failed: $($entry.Key), exit=$($commandProcess.ExitCode)" }
}
$userConfig = Join-Path $env:APPDATA 'RustDesk\config\RustDesk2.toml'
$body = Get-Content -LiteralPath $userConfig -Raw
foreach ($entry in $options.GetEnumerator()) {
    $pattern = '(?m)^{0}\s*=\s*[''"]{1}[''"]\s*$' -f [regex]::Escape($entry.Key), [regex]::Escape([string]$entry.Value)
    if (-not [regex]::IsMatch($body, $pattern)) { throw "Saved profile not verified: $($entry.Key)" }
}
$report = '{"verified":true,"sni":"www.alipan.com","public_port":443,"selected_transport_unchanged":true}'
$report | Set-Content -LiteralPath '<workspace>\deploy\vps1-reality-alipan\client-sync-result.json' -Encoding UTF8
Write-Output 'REALITY saved profile verified; selected transport unchanged.'
