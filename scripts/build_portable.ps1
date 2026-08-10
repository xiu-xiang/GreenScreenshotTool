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

Write-Host "[1/4] Ensure offline models exist..." -ForegroundColor Cyan
& $Py (Join-Path $PSScriptRoot "download_models.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/4] PyInstaller pack..." -ForegroundColor Cyan
& $Py -m PyInstaller --noconfirm --clean --windowed --name ShotPortable `
  --paths $Root `
  --distpath $Dist `
  --workpath $Work `
  --specpath $Root `
  --collect-all rapidocr_onnxruntime `
  --collect-all onnxruntime `
  --collect-all argostranslate `
  --collect-all ctranslate2 `
  --exclude-module torch `
  --exclude-module torchvision `
  --exclude-module torchaudio `
  --exclude-module spacy `
  --exclude-module stanza `
  --exclude-module thinc `
  --exclude-module blis `
  --hidden-import pynput.keyboard._win32 `
  --hidden-import pynput.mouse._win32 `
  --hidden-import pystray._win32 `
  (Join-Path $Root "run.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/4] Assemble green folder..." -ForegroundColor Cyan
$built = Join-Path $Dist "ShotPortable"
if (-not (Test-Path $built)) {
    Write-Host ("Build output missing: {0}" -f $built) -ForegroundColor Red
    exit 1
}

if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item (Join-Path $built "*") $Out -Recurse -Force

# 关键：只发布已安装模型，不带 .argosmodel / cache（体积更小）
$modelsSrcInstalled = Join-Path $Root "models\argos_installed"
if (-not (Test-Path $modelsSrcInstalled) -or -not (Get-ChildItem $modelsSrcInstalled -Directory -ErrorAction SilentlyContinue)) {
    Write-Host "models/argos_installed missing. Run download_models.py first." -ForegroundColor Red
    exit 1
}

function Copy-RuntimeModels([string]$targetRoot) {
    $dst = Join-Path $targetRoot "models"
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item $modelsSrcInstalled (Join-Path $dst "argos_installed") -Recurse -Force
    # 删除包内 stanza（离线分句不用）
    Get-ChildItem (Join-Path $dst "argos_installed") -Recurse -Directory -Filter "stanza" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
}

Copy-RuntimeModels $Out
Copy-RuntimeModels $built
Write-Host "runtime models copied (argos_installed only)" -ForegroundColor Green

function Remove-PublishBloat([string]$targetRoot) {
    # 剔除误打进包的重依赖与缓存（翻译/OCR 运行时不需要）
    $junk = @(
        "torch", "torchvision", "torchaudio",
        "spacy", "spacy_legacy", "spacy_loggers",
        "stanza", "thinc", "blis", "srsly", "preshed", "cymem", "murmurhash",
        "catalogue", "confection", "wasabi", "typer", "smart_open", "cloudpathlib",
        "langcodes"
    )
    $internal = Join-Path $targetRoot "_internal"
    foreach ($name in $junk) {
        $p = Join-Path $internal $name
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force
            Write-Host ("removed bloat: {0}" -f $name) -ForegroundColor DarkYellow
        }
        Get-ChildItem $internal -Directory -Filter ($name + "*") -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like ($name + "-*") -or $_.Name -eq $name } |
            ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
    }
    foreach ($extra in @("models\argos_cache", "models\argos_data", "models\argos")) {
        $p = Join-Path $targetRoot $extra
        if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
}

Write-Host "[4/4] Patch offline runtime + strip bloat..." -ForegroundColor Cyan
$sbdSrc = Join-Path $PSScriptRoot "argos_sbd_offline.py"
foreach ($targetRoot in @($Out, $built)) {
    $sbdDst = Join-Path $targetRoot "_internal\argostranslate\sbd.py"
    if (Test-Path (Split-Path $sbdDst -Parent)) {
        Copy-Item $sbdSrc $sbdDst -Force
        Write-Host ("patched offline sbd -> {0}" -f $sbdDst) -ForegroundColor Green
    }
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
                $txt2 = $txt -replace '(?s)try:\r?\n\s*import torch\r?\n\r?\n\s*torch_is_available = True\r?\nexcept ImportError:\r?\n\s*torch_is_available = False', $new.Trim()
            }
            Set-Content -Path $spec -Value $txt2 -Encoding UTF8
            Write-Host ("patched no-torch ctranslate2 -> {0}" -f $spec) -ForegroundColor Green
        }
    }
    Remove-PublishBloat $targetRoot
}

$readme = Join-Path $Root "使用说明.txt"
if (Test-Path $readme) { Copy-Item $readme $Out -Force }

$icon = Join-Path $Root "assets\app.ico"
if (Test-Path $icon) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Out "assets") | Out-Null
    Copy-Item $icon (Join-Path $Out "assets\app.ico") -Force
}

$sizeGB = [math]::Round(((Get-ChildItem $Out -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB), 2)
Write-Host ""
Write-Host ("Green package ready: {0}" -f $Out) -ForegroundColor Green
Write-Host ("Approx size: {0} GB" -f $sizeGB) -ForegroundColor Yellow
Write-Host "Copy the whole folder to any Win10+ x64 PC and run ShotPortable.exe" -ForegroundColor Green
Write-Host "Default offline. Enable online only via editor checkbox for current session." -ForegroundColor Yellow
