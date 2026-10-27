param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path "vendor\JUCE\CMakeLists.txt")) {
    Write-Host "Cloning JUCE 8.0.6..."
    git clone --depth 1 --branch 8.0.6 https://github.com/juce-framework/JUCE.git vendor/JUCE
}

python -m pip install --quiet cmake ninja | Out-Null

python -m cmake -S . -B build -G "Visual Studio 18 2026" -A x64
python -m cmake --build build --config $Configuration --target BandLabWhiteBox_VST3 BandLabWhiteBox_Standalone

$vst = Get-ChildItem "build\BandLabWhiteBox_artefacts\$Configuration\VST3" -Directory -Filter "*.vst3" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($vst) {
    Write-Host "VST3: $($vst.FullName)"
} else {
    Write-Host "VST3 artifact not found."
}
$standalone = Get-ChildItem "build\BandLabWhiteBox_artefacts\$Configuration\Standalone" -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($standalone) {
    Write-Host "Standalone: $($standalone.FullName)"
}
