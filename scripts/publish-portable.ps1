# 发布绿色便携版（单文件夹自包含，可拷贝到任意 Windows x64 机器运行）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$proj = Join-Path $root "ScreenshotTool\ScreenshotTool.csproj"
$out  = Join-Path $root "dist\ScreenshotTool-Portable"

Write-Host "开始发布便携版..." -ForegroundColor Cyan
dotnet publish $proj -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true `
  -p:EnableCompressionInSingleFile=true `
  -p:PublishTrimmed=false `
  -o $out

# 确保模型目录随发布输出
$modelsSrc = Join-Path $root "ScreenshotTool\models"
$modelsDst = Join-Path $out "models"
if (Test-Path $modelsSrc) {
  Copy-Item -Path $modelsSrc -Destination $modelsDst -Recurse -Force
}

Write-Host ""
Write-Host "发布完成: $out" -ForegroundColor Green
Write-Host "请先运行 download-models.ps1 下载 OCR 模型，再分发整个文件夹。" -ForegroundColor Yellow
