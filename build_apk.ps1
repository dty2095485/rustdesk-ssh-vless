& "$PSScriptRoot\scripts\build\build_apk.ps1" @args
if (!$?) { throw 'Android packaging failed' }
