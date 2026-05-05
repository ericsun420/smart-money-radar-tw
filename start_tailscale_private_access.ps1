param(
  [string]$AccessToken = $env:SMART_MONEY_ACCESS_TOKEN,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }
$Tailscale = "C:\Program Files\Tailscale\tailscale.exe"

if (-not (Test-Path $Tailscale)) {
  throw "Tailscale CLI not found. Install Tailscale first: https://tailscale.com/download/windows"
}

if (-not $AccessToken) {
  $tokenFile = Join-Path $BackendRoot "public_access_token.txt"
  if (Test-Path $tokenFile) {
    $AccessToken = (Get-Content $tokenFile -Raw).Trim()
  }
}
if (-not $AccessToken) {
  $AccessToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
}

$env:SMART_MONEY_ACCESS_TOKEN = $AccessToken
Set-Content -Path (Join-Path $BackendRoot "public_access_token.txt") -Value $AccessToken -Encoding ascii

$statusJson = & $Tailscale status --json | ConvertFrom-Json
$dnsName = [string]$statusJson.Self.DNSName
$dnsName = $dnsName.TrimEnd(".")
if (-not $dnsName) {
  throw "Could not read Tailscale DNSName. Make sure Tailscale is logged in and MagicDNS is enabled."
}

Write-Host ""
Write-Host "Starting Smart Money Radar for Tailscale private access..."
Write-Host "Tailscale URL:"
Write-Host "  http://$dnsName`:$Port/?token=$AccessToken"
Write-Host ""
Write-Host "Phone requirement: install Tailscale and log in to the same account."
Write-Host ""

Set-Location $BackendRoot
$env:SMART_MONEY_ACCESS_TOKEN = $AccessToken
& $Python -m uvicorn app.main:app --host 0.0.0.0 --port $Port

