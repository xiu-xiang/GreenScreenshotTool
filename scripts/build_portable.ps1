# Build portable green package for Win10+ x64 (no Python/Docker required on target PC)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build"
$Out = Join-Path $Root "dist\ShotPortable-Green"

if (-not (Test-Path $Py)) {
    Write-Host "venv not found. Create .venv and install requirements first." -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Ensure offline models exist..." -ForegroundColor Cyan
& $Py (Join-Path $PSScriptRoot "download_models.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] PyInstaller pack..." -ForegroundColor Cyan
& $Py -m PyInstaller --noconfirm --clean --windowed --name ShotPortable `
  --paths $Root `
  --distpath $Dist `
  --workpath $Work `
  --specpath $Root `
  --collect-all rapidocr_onnxruntime `
  --collect-all onnxruntime `
  --collect-all argostranslate `
  --collect-all ctranslate2 `
  --hidden-import pynput.keyboard._win32 `
  --hidden-import pynput.mouse._win32 `
  --hidden-import pystray._win32 `
  (Join-Path $Root "run.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/3] Assemble green folder..." -ForegroundColor Cyan
$built = Join-Path $Dist "ShotPortable"
if (-not (Test-Path $built)) {
    Write-Host ("Build output missing: {0}" -f $built) -ForegroundColor Red
    exit 1
}

if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item (Join-Path $built "*") $Out -Recurse -Force

$modelsSrc = Join-Path $Root "models"
$modelsDst = Join-Path $Out "models"
if (Test-Path $modelsSrc) {
    Copy-Item $modelsSrc $modelsDst -Recurse -Force
}

$readme = Join-Path $Root "使用说明.txt"
if (Test-Path $readme) { Copy-Item $readme $Out -Force }

$icon = Join-Path $Root "assets\app.ico"
if (Test-Path $icon) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Out "assets") | Out-Null
    Copy-Item $icon (Join-Path $Out "assets\app.ico") -Force
}

# Size summary
$sizeGB = [math]::Round(((Get-ChildItem $Out -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB), 2)
Write-Host ""
Write-Host ("Green package ready: {0}" -f $Out) -ForegroundColor Green
Write-Host ("Approx size: {0} GB" -f $sizeGB) -ForegroundColor Yellow
Write-Host "Copy the whole folder to any Win10+ x64 PC and run ShotPortable.exe" -ForegroundColor Green
Write-Host "Default offline. Enable online only via editor checkbox for current session." -ForegroundColor Yellow
