$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

$bundle = "build\BandLabWhiteBox_artefacts\Release\VST3\BandLab WhiteBox Suite.vst3"
& ".\build\Release\juce_vst3_helper.exe" -validate -path $bundle
Write-Output ("validate exit=" + $LASTEXITCODE)
Get-Item $bundle | ForEach-Object { Write-Output ("bundle: " + $_.FullName + " " + $_.LastWriteTime) }
Get-ChildItem "build\BandLabWhiteBox_artefacts\Release\Standalone" -Filter *.exe | ForEach-Object {
    Write-Output ("standalone: " + $_.FullName + " " + $_.LastWriteTime)
}
