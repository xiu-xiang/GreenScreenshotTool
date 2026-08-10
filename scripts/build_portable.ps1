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

# 关键：models 必须与 exe 同级，否则离线翻译找不到包
$modelsSrc = Join-Path $Root "models"
$modelsDst = Join-Path $Out "models"
if (-not (Test-Path (Join-Path $modelsSrc "argos"))) {
    Write-Host "models/argos missing. Run download_models.py first." -ForegroundColor Red
    exit 1
}
if (Test-Path $modelsDst) { Remove-Item $modelsDst -Recurse -Force }
Copy-Item $modelsSrc $modelsDst -Recurse -Force
# 同步一份到 PyInstaller 输出目录，方便直接跑 dist\ShotPortable
$builtModels = Join-Path $built "models"
if (Test-Path $builtModels) { Remove-Item $builtModels -Recurse -Force }
Copy-Item $modelsSrc $builtModels -Recurse -Force
Write-Host "models copied beside exe" -ForegroundColor Green

# 覆盖 Argos 分句模块：禁止 stanza/torch，避免对照翻译卡住
$sbdSrc = Join-Path $PSScriptRoot "argos_sbd_offline.py"
foreach ($targetRoot in @($Out, $built)) {
    $sbdDst = Join-Path $targetRoot "_internal\argostranslate\sbd.py"
    if (Test-Path (Split-Path $sbdDst -Parent)) {
        Copy-Item $sbdSrc $sbdDst -Force
        Write-Host ("patched offline sbd -> {0}" -f $sbdDst) -ForegroundColor Green
    }
    # 禁止 ctranslate2 导入 torch（推理不需要，导入会假死）
    $spec = Join-Path $targetRoot "_internal\ctranslate2\specs\model_spec.py"
    if (Test-Path $spec) {
        $txt = Get-Content $spec -Raw -Encoding UTF8
        $old = @'
try:
    import torch

    torch_is_available = True
except ImportError:
    torch_is_available = False
'@
        $new = @'
# 绿色包热补丁：翻译推理不需要 torch；导入 torch 会导致首次对照翻译长时间假死
torch_is_available = False
torch = None
'@
        if ($txt -like "*torch_is_available = True*") {
            $txt2 = $txt.Replace($old, $new)
            if ($txt2 -eq $txt) {
                # 容错：按行粗替换
                $txt2 = $txt -replace '(?s)try:\r?\n\s*import torch\r?\n\r?\n\s*torch_is_available = True\r?\nexcept ImportError:\r?\n\s*torch_is_available = False', $new.Trim()
            }
            Set-Content -Path $spec -Value $txt2 -Encoding UTF8
            Write-Host ("patched no-torch ctranslate2 -> {0}" -f $spec) -ForegroundColor Green
        }
    }
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
