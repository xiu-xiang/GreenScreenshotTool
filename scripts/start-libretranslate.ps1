# Start local LibreTranslate with Docker for ScreenshotTool
# Usage:
#   .\scripts\start-libretranslate.ps1
#   .\scripts\start-libretranslate.ps1 -Port 5001

param(
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if ($Port -le 0) {
    $candidates = @(
        (Join-Path (Split-Path -Parent $PSScriptRoot) "ScreenshotTool\bin\Release\net8.0-windows\settings.json"),
        (Join-Path (Split-Path -Parent $PSScriptRoot) "ScreenshotTool\settings.json")
    )
    foreach ($settingsPath in $candidates) {
        if (-not (Test-Path $settingsPath)) { continue }
        try {
            $json = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($json.libreTranslatePort) { $Port = [int]$json.libreTranslatePort; break }
            if ($json.LibreTranslatePort) { $Port = [int]$json.LibreTranslatePort; break }
        } catch { }
    }
}
if ($Port -le 0) { $Port = 5000 }

Write-Host ("Starting LibreTranslate on http://127.0.0.1:{0}" -f $Port) -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not found. Install Docker Desktop, or use Python:" -ForegroundColor Red
    Write-Host ("  pip install libretranslate") -ForegroundColor Yellow
    Write-Host ("  libretranslate --host 127.0.0.1 --port {0}" -f $Port) -ForegroundColor Yellow
    exit 1
}

$container = "screenshottool-libretranslate"
$exists = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $container }
if ($exists) {
    Write-Host "Removing old container..." -ForegroundColor DarkGray
    docker rm -f $container | Out-Null
}

Write-Host "Pulling/starting image (first run may take a while)..." -ForegroundColor Yellow
docker run -d --name $container `
    -p ("{0}:5000" -f $Port) `
    --restart unless-stopped `
    libretranslate/libretranslate | Out-Null

Write-Host "Waiting for service..." -ForegroundColor Yellow
$url = "http://127.0.0.1:{0}/languages" -f $Port
$ok = $false
for ($i = 1; $i -le 90; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch {
        Start-Sleep -Seconds 2
    }
    if (($i % 10) -eq 0) {
        Write-Host ("  still waiting... {0}s" -f ($i * 2)) -ForegroundColor DarkGray
    }
}

if ($ok) {
    Write-Host ("LibreTranslate ready: http://127.0.0.1:{0}" -f $Port) -ForegroundColor Green
    Write-Host "Open ScreenshotTool settings, click Detect, then translate again." -ForegroundColor Green
    exit 0
}

Write-Host "Container started but service not ready yet (models loading)." -ForegroundColor Yellow
Write-Host ("Check logs: docker logs -f {0}" -f $container) -ForegroundColor DarkGray
exit 2
