Add-Type @'
using System;
using System.Runtime.InteropServices;
public class WInfo {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  public struct RECT { public int L, T, R, B; }
}
'@
$p = Get-Process -Name "BandLab WhiteBox Suite" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Output "not running"; exit 1 }
$h = $p.MainWindowHandle
[WInfo]::SetWindowPos($h, [IntPtr]::Zero, 0, 0, 0, 0, 0x0001 -bor 0x0004) | Out-Null
$wr = New-Object WInfo+RECT
$cr = New-Object WInfo+RECT
[WInfo]::GetWindowRect($h, [ref]$wr) | Out-Null
[WInfo]::GetClientRect($h, [ref]$cr) | Out-Null
$dpi = [WInfo]::GetDpiForWindow($h)
Write-Output ("window={0}x{1} client={2}x{3} dpi={4}" -f ($wr.R-$wr.L), ($wr.B-$wr.T), $cr.R, $cr.B, $dpi)
