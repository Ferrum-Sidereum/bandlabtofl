Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class WCap3 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  public struct RECT { public int L, T, R, B; }
}
'@
$p = Get-Process -Name "BandLab WhiteBox Suite" -ErrorAction Stop | Select-Object -First 1
$h = $p.MainWindowHandle
[WCap3]::ShowWindow($h, 9) | Out-Null
Start-Sleep -Milliseconds 700
$r = New-Object WCap3+RECT
[WCap3]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [WCap3]::PrintWindow($h, $hdc, 2)
$g.ReleaseHdc($hdc)
$bmp.Save('C:\Users\Flusion\projects\bandlabtofl\dev\standalone.png')
Write-Output ("{0} {1}x{2}" -f $ok, $w, $ht)
