param(
  [string]$AccessToken = $env:SMART_MONEY_ACCESS_TOKEN,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

if (-not $AccessToken) {
  $AccessToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$LocalCloudflared = Join-Path $ProjectRoot "tools\cloudflared.exe"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }
$Cloudflared = if (Test-Path $LocalCloudflared) { $LocalCloudflared } else { "cloudflared" }

if (-not (Test-Path $LocalCloudflared) -and -not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared was not found."
  Write-Host "Install Cloudflare Tunnel CLI first:"
  Write-Host "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
}

Write-Host ""
Write-Host "Smart Money Radar public tunnel mode"
Write-Host "Access Token: $AccessToken"
Write-Host "After cloudflared prints an https URL, open this on your phone:"
Write-Host "https://generated-cloudflare-url/?token=$AccessToken"
Write-Host ""

$env:SMART_MONEY_ACCESS_TOKEN = $AccessToken

$serverArgs = @(
  "-m", "uvicorn", "app.main:app",
  "--host", "127.0.0.1",
  "--port", "$Port"
)

Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $BackendRoot -WindowStyle Hidden
Start-Sleep -Seconds 3

& $Cloudflared tunnel --url "http://127.0.0.1:${Port}"
