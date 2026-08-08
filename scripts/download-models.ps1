# 说明：当前版本 OCR 已切换为开源 PaddleOCR
# 中英模型随 NuGet（PaddleOCRSharp）自动复制到输出目录 inference/，一般无需再下载。
#
# 本脚本保留用于兼容旧版 Tesseract 模型（可选，非必需）。

$ErrorActionPreference = "Stop"
Write-Host "当前截图工具使用 PaddleOCR，编译/发布后会自动带上 inference 模型。" -ForegroundColor Green
Write-Host "无需执行本脚本即可识别中文。" -ForegroundColor Cyan
Write-Host ""
Write-Host "若仍需下载旧版 Tesseract 模型，请取消下面注释后重跑。" -ForegroundColor DarkGray

<#
$root = Split-Path -Parent $PSScriptRoot
$tessDir = Join-Path $root "ScreenshotTool\models\tessdata"
New-Item -ItemType Directory -Force -Path $tessDir | Out-Null
$files = @{
  "eng.traineddata"     = "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"
  "chi_sim.traineddata" = "https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata"
}
foreach ($name in $files.Keys) {
  $dest = Join-Path $tessDir $name
  if (Test-Path $dest) { continue }
  Invoke-WebRequest -Uri $files[$name] -OutFile $dest -UseBasicParsing
}
#>
