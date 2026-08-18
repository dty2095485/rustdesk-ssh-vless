param(
    [string]$OutPath = 'D:\chatgpt\vps-deploy\rustdesk_window2.png',
    [switch]$Ocr
)
$ErrorActionPreference = 'Stop'
$procs = Get-Process rustdesk -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }
if (-not $procs) { throw 'rustdesk window not found' }
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
public static class W32 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  public static List<IntPtr> FindWindows(int pid, string titlePart) {
    var found = new List<IntPtr>();
    EnumWindows((h, l) => {
      uint p;
      GetWindowThreadProcessId(h, out p);
      if (p == (uint)pid && IsWindowVisible(h)) {
        var len = GetWindowTextLength(h);
        if (len > 0) {
          var sb = new StringBuilder(len + 1);
          GetWindowText(h, sb, sb.Capacity);
          if (titlePart.Length == 0 || sb.ToString().Contains(titlePart)) found.Add(h);
        }
      }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
}
'@
$best = $null
$bestArea = 0
foreach ($proc in $procs) {
    $wins = [W32]::FindWindows($proc.Id, '')
    foreach ($w in $wins) {
        $r = New-Object RECT
        [W32]::GetWindowRect($w, [ref]$r) | Out-Null
        $area = ($r.Right - $r.Left) * ($r.Bottom - $r.Top)
        if ($area -gt $bestArea) { $bestArea = $area; $best = $w; $bestProc = $proc }
    }
}
if (-not $best) { throw 'no visible rustdesk window found' }
[W32]::ShowWindow($best, 9) | Out-Null   # SW_RESTORE
Start-Sleep -Milliseconds 400
[W32]::SetForegroundWindow($best) | Out-Null
Start-Sleep -Milliseconds 600
$r = New-Object RECT
[W32]::GetWindowRect($best, [ref]$r) | Out-Null
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
if ($w -le 0 -or $h -le 0) { throw "bad window rect $w x $h" }
$b = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($b)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $b.Size)
$b.Save($OutPath)
$g.Dispose()
$b.Dispose()
Write-Output "captured ${w}x${h} -> $OutPath"
if ($Ocr) { & 'D:\chatgpt\vps-deploy\ocr.ps1' -ImagePath $OutPath }
