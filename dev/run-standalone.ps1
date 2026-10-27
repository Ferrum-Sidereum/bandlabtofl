$exe = "C:\Users\Flusion\projects\bandlabtofl\build\BandLabWhiteBox_artefacts\Release\Standalone\BandLab WhiteBox Suite.exe"
Start-Process -FilePath $exe
Start-Sleep -Seconds 12
Get-Process -Name "BandLab WhiteBox Suite" -ErrorAction SilentlyContinue | Select-Object Id, MainWindowTitle, Responding
