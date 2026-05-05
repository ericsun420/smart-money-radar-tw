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
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
  Write-Host "ngrok was not found."
  Write-Host "Install ngrok and configure your authtoken first:"
  Write-Host "https://ngrok.com/docs/getting-started/"
  exit 1
}

Write-Host ""
Write-Host "Smart Money Radar ngrok public tunnel mode"
Write-Host "Access Token: $AccessToken"
Write-Host "After ngrok prints an https URL, open this on your phone:"
Write-Host "https://generated-ngrok-url/?token=$AccessToken"
Write-Host ""

$env:SMART_MONEY_ACCESS_TOKEN = $AccessToken

$serverArgs = @(
  "-m", "uvicorn", "app.main:app",
  "--host", "127.0.0.1",
  "--port", "$Port"
)

Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $BackendRoot -WindowStyle Hidden
Start-Sleep -Seconds 3

ngrok http $Port
