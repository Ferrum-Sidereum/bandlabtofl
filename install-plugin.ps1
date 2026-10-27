param(
    [string]$Configuration = "Release",
    [switch]$UserOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Get-ChildItem (Join-Path $root "build\BandLabWhiteBox_artefacts\$Configuration\VST3") -Directory -Filter "*.vst3" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $source) {
    throw "Build the plugin first: .\build-plugin.ps1"
}

if ($UserOnly) {
    $target = Join-Path $env:LOCALAPPDATA "Programs\Common\VST3"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Recurse -Force $source.FullName $target
    Write-Host "Installed to $target"
    Write-Host "Add this folder to FL Studio: Options > Manage plug-ins > VST3 search paths."
    exit 0
}

$target = "C:\Program Files\Common Files\VST3"
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as administrator, or use -UserOnly."
}
Copy-Item -Recurse -Force $source.FullName $target
Write-Host "Installed to $target"
Write-Host "In FL Studio: Options > Manage plug-ins > Find more plug-ins."
