Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class WCap4 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  public struct RECT { public int L, T, R, B; }
}
'@
$p = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*BL2FLP*" } | Select-Object -First 1
if (-not $p) { Write-Output "no BL2FLP window"; exit 1 }
$h = $p.MainWindowHandle
[WCap4]::ShowWindow($h, 9) | Out-Null
Start-Sleep -Milliseconds 700
$r = New-Object WCap4+RECT
[WCap4]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [WCap4]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$bmp.Save('C:\Users\Flusion\projects\bandlabtofl\dev\gui.png')
Write-Output ("{0} {1}x{2} title={3}" -f $ok, $w, $ht, $p.MainWindowTitle)
