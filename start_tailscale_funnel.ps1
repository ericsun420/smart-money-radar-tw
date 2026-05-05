param(
  [string]$AccessToken = $env:SMART_MONEY_ACCESS_TOKEN,
  [string]$AdminToken = $env:SMART_MONEY_ADMIN_TOKEN,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }
$TailscaleCandidates = @(
  "tailscale",
  "C:\Program Files\Tailscale\tailscale.exe",
  "C:\Program Files (x86)\Tailscale\tailscale.exe"
)

$Tailscale = $null
foreach ($candidate in $TailscaleCandidates) {
  if ($candidate -eq "tailscale") {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) {
      $Tailscale = $cmd.Source
      break
    }
  } elseif (Test-Path $candidate) {
    $Tailscale = $candidate
    break
  }
}

if (-not $Tailscale) {
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
if ($AdminToken) {
  $env:SMART_MONEY_ADMIN_TOKEN = $AdminToken
}
Set-Content -Path (Join-Path $BackendRoot "public_access_token.txt") -Value $AccessToken -Encoding ascii

Write-Host ""
Write-Host "Smart Money Radar Tailscale Funnel"
Write-Host "Origin : http://127.0.0.1:$Port"
Write-Host "Token  : $AccessToken"
Write-Host ""

try {
  $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -Headers @{ "x-smart-money-token" = $AccessToken } -TimeoutSec 5
  Write-Host "Origin already running. Data source: $($health.data_source) / $($health.data_source_status)"
} catch {
  Write-Host "Starting origin server..."
  Start-Process -FilePath $Python -ArgumentList @("run_origin_server.py") -WorkingDirectory $BackendRoot -WindowStyle Hidden
  Start-Sleep -Seconds 6
  $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -Headers @{ "x-smart-money-token" = $AccessToken } -TimeoutSec 15
  Write-Host "Origin health OK. Data source: $($health.data_source) / $($health.data_source_status)"
}

Write-Host ""
Write-Host "Checking Tailscale status..."
$statusJson = & $Tailscale status --json | ConvertFrom-Json
$dnsName = [string]$statusJson.Self.DNSName
$dnsName = $dnsName.TrimEnd(".")
$capabilities = @($statusJson.Self.Capabilities)
if ($capabilities -notcontains "funnel") {
  Write-Host ""
  Write-Host "Tailscale HTTPS is available, but Funnel ACL permission is still missing."
  Write-Host "Current DNS name: $dnsName"
  Write-Host ""
  Write-Host "Open Tailscale admin console > Access controls and add:"
  Write-Host '"nodeAttrs": ['
  Write-Host '  {'
  Write-Host '    "target": ["autogroup:member"],'
  Write-Host '    "attr": ["funnel"]'
  Write-Host '  }'
  Write-Host ']'
  Write-Host ""
  throw "Missing Tailscale funnel capability in this node status."
}
& $Tailscale status | Out-Host

Write-Host ""
Write-Host "Starting Tailscale Funnel in background..."
& $Tailscale funnel --yes --bg $Port

Write-Host ""
Write-Host "Funnel status:"
$status = & $Tailscale funnel status 2>&1 | Out-String
Write-Host $status

$url = $null
if ($status -match "https://[^\s]+") {
  $url = $Matches[0].TrimEnd("/")
}

if ($url) {
  Write-Host ""
  Write-Host "Open this on your phone:"
  Write-Host "$url/?token=$AccessToken"
} else {
  Write-Host ""
  Write-Host "If no URL is shown above, open Tailscale admin console and enable Funnel for this device, then rerun this script."
}
