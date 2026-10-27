Get-Service | Where-Object { $_.Name -match 'Image|FL' -or $_.DisplayName -match 'Image-Line|FL Studio' } |
    Select-Object Name, Status, StartType

Get-Process FL64 -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -FilePath 'C:\Program Files\Image-Line\FL Studio 2026\FL64.exe'
Start-Sleep -Seconds 45
Get-Process FL64 -ErrorAction SilentlyContinue | Select-Object Id, MainWindowTitle, Responding, CPU
