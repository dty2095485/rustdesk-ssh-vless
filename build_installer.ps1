# Forward all named/positional arguments to the maintained packaging entry point.
& "$PSScriptRoot\scripts\build\build_installer.ps1" @args
if (!$?) { throw 'Installer packaging failed' }
