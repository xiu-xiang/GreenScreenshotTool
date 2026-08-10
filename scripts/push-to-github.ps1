# Push main (Python) + csharp branches to a new GitHub repo.
# Usage:
#   1) Create a classic PAT with repo scope: https://github.com/settings/tokens
#   2) .\scripts\push-to-github.ps1 -Token ghp_xxx [-RepoName GreenScreenshotTool] [-Private]

param(
    [Parameter(Mandatory = $true)]
    [string]$Token,
    [string]$RepoName = "GreenScreenshotTool",
    [switch]$Private
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

$Token | gh auth login --with-token
gh auth setup-git

$visibility = if ($Private) { "--private" } else { "--public" }

# Create repo if remote missing
$hasRemote = $false
try { git remote get-url origin | Out-Null; $hasRemote = $true } catch { $hasRemote = $false }

if (-not $hasRemote) {
    gh repo create $RepoName $visibility --source=. --remote=origin --description "Green portable screenshot tool (Python main + C# branch)"
} else {
    Write-Host "origin already exists, skip create"
}

git checkout main
git push -u origin main
git push -u origin csharp

Write-Host ""
Write-Host "Done." -ForegroundColor Green
gh repo view --web
