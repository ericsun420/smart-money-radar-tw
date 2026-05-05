param(
  [string]$Hostname = $env:SMART_MONEY_PUBLIC_HOSTNAME,
  [string]$TunnelName = $env:SMART_MONEY_TUNNEL_NAME,
  [string]$AccessToken = $env:SMART_MONEY_ACCESS_TOKEN,
  [string]$AdminToken = $env:SMART_MONEY_ADMIN_TOKEN,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$EnvPath = Join-Path $ProjectRoot ".smart-money-radar.env.ps1"
$CloudflaredLocal = Join-Path $ProjectRoot "tools\cloudflared.exe"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }
$Cloudflared = if (Test-Path $CloudflaredLocal) { $CloudflaredLocal } else { "cloudflared" }

if (Test-Path $EnvPath) {
  . $EnvPath
}

if (-not $Hostname) { $Hostname = $env:SMART_MONEY_PUBLIC_HOSTNAME }
if (-not $TunnelName) { $TunnelName = $env:SMART_MONEY_TUNNEL_NAME }
if (-not $AccessToken) { $AccessToken = $env:SMART_MONEY_ACCESS_TOKEN }
if (-not $AdminToken) { $AdminToken = $env:SMART_MONEY_ADMIN_TOKEN }

if (-not $Hostname) { throw "Hostname is required. Example: -Hostname radar.example.com" }
if (-not $TunnelName) { $TunnelName = "smart-money-radar" }
if (-not $AccessToken) { throw "SMART_MONEY_ACCESS_TOKEN is required. Run setup_cloudflare_named_tunnel.ps1 first." }

$ConfigPath = $env:SMART_MONEY_TUNNEL_CONFIG
if (-not $ConfigPath) {
  $ConfigPath = Join-Path $env:USERPROFILE ".cloudflared\$TunnelName.yml"
}
if (-not (Test-Path $ConfigPath)) {
  throw "Tunnel config not found: $ConfigPath. Run setup_cloudflare_named_tunnel.ps1 first."
}

$env:SMART_MONEY_ACCESS_TOKEN = $AccessToken
if ($AdminToken) {
  $env:SMART_MONEY_ADMIN_TOKEN = $AdminToken
}
$env:SMART_MONEY_CORS_ORIGINS = "http://127.0.0.1:${Port},http://localhost:${Port},https://$Hostname"

Set-Content -Path (Join-Path $BackendRoot "public_access_token.txt") -Value $AccessToken -Encoding ascii

Write-Host ""
Write-Host "Starting Smart Money Radar origin server..."
Write-Host "Origin : http://127.0.0.1:$Port"
Write-Host "Public : https://$Hostname/?token=$AccessToken"
Write-Host ""

try {
  $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -Headers @{ "x-smart-money-token" = $AccessToken } -TimeoutSec 10
  Write-Host "Origin already running. Data source: $($health.data_source) / $($health.data_source_status)"
} catch {
  $serverArgs = @("run_origin_server.py")
  Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $BackendRoot -WindowStyle Hidden
  Start-Sleep -Seconds 5
  try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -Headers @{ "x-smart-money-token" = $AccessToken } -TimeoutSec 10
    Write-Host "Origin health OK. Data source: $($health.data_source) / $($health.data_source_status)"
  } catch {
    Write-Host "Origin health check failed. The tunnel will still start, but Cloudflare may show 502 until origin is ready."
  }
}

Write-Host ""
Write-Host "Starting Cloudflare named tunnel..."
Write-Host "Config: $ConfigPath"
Write-Host ""

& $Cloudflared tunnel --config $ConfigPath run $TunnelName
