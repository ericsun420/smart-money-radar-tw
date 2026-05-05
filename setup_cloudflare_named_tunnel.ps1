param(
  [Parameter(Mandatory = $true)]
  [string]$Hostname,

  [string]$TunnelName = "smart-money-radar",
  [string]$AccessToken = $env:SMART_MONEY_ACCESS_TOKEN,
  [string]$AdminToken = $env:SMART_MONEY_ADMIN_TOKEN,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CloudflaredLocal = Join-Path $ProjectRoot "tools\cloudflared.exe"
$Cloudflared = if (Test-Path $CloudflaredLocal) { $CloudflaredLocal } else { "cloudflared" }
$CloudflaredHome = Join-Path $env:USERPROFILE ".cloudflared"
$ConfigPath = Join-Path $CloudflaredHome "$TunnelName.yml"

if (-not (Test-Path $CloudflaredLocal) -and -not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  throw "cloudflared not found. Put cloudflared.exe under tools\ or install it in PATH."
}

if (-not $AccessToken) {
  $AccessToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
}

if (-not $AdminToken) {
  $AdminToken = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
}

New-Item -ItemType Directory -Force -Path $CloudflaredHome | Out-Null

Write-Host ""
Write-Host "Smart Money Radar Cloudflare named tunnel setup"
Write-Host "Hostname   : https://$Hostname"
Write-Host "TunnelName : $TunnelName"
Write-Host ""

$CertPath = Join-Path $CloudflaredHome "cert.pem"
if (-not (Test-Path $CertPath)) {
  Write-Host "Step 1/5: Cloudflare login is required."
  Write-Host "A browser will open. Log in and select the domain that owns $Hostname."
  & $Cloudflared tunnel login
} else {
  Write-Host "Step 1/5: Cloudflare cert already exists: $CertPath"
}

Write-Host "Step 2/5: Create tunnel if needed."
$TunnelListText = & $Cloudflared tunnel list 2>&1 | Out-String
if ($TunnelListText -notmatch [regex]::Escape($TunnelName)) {
  & $Cloudflared tunnel create $TunnelName
} else {
  Write-Host "Tunnel already exists: $TunnelName"
}

$TunnelInfo = & $Cloudflared tunnel info $TunnelName 2>&1 | Out-String
$TunnelId = $null
if ($TunnelInfo -match "([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})") {
  $TunnelId = $Matches[1]
}
if (-not $TunnelId) {
  throw "Could not determine tunnel UUID. Run: $Cloudflared tunnel info $TunnelName"
}

$CredentialsFile = Join-Path $CloudflaredHome "$TunnelId.json"
if (-not (Test-Path $CredentialsFile)) {
  throw "Tunnel credentials file not found: $CredentialsFile"
}

Write-Host "Step 3/5: Write local tunnel config: $ConfigPath"
@"
tunnel: $TunnelId
credentials-file: $($CredentialsFile -replace "\\", "/")

ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:$Port
  - service: http_status:404
"@ | Set-Content -Path $ConfigPath -Encoding utf8

Write-Host "Step 4/5: Route DNS hostname to tunnel."
& $Cloudflared tunnel route dns $TunnelName $Hostname

Write-Host "Step 5/5: Save token helper files."
Set-Content -Path (Join-Path $ProjectRoot "backend\public_access_token.txt") -Value $AccessToken -Encoding ascii
$EnvPath = Join-Path $ProjectRoot ".smart-money-radar.env.ps1"
@"
`$env:SMART_MONEY_ACCESS_TOKEN = "$AccessToken"
`$env:SMART_MONEY_ADMIN_TOKEN = "$AdminToken"
`$env:SMART_MONEY_CORS_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000,https://$Hostname"
`$env:SMART_MONEY_PUBLIC_HOSTNAME = "$Hostname"
`$env:SMART_MONEY_TUNNEL_NAME = "$TunnelName"
`$env:SMART_MONEY_TUNNEL_CONFIG = "$ConfigPath"
"@ | Set-Content -Path $EnvPath -Encoding utf8

Write-Host ""
Write-Host "Setup complete."
Write-Host "Public URL:"
Write-Host "  https://$Hostname/?token=$AccessToken"
Write-Host ""
Write-Host "Admin token was written only to .smart-money-radar.env.ps1."
Write-Host "Start it with:"
Write-Host "  .\start_cloudflare_named_tunnel.ps1 -Hostname $Hostname"
Write-Host ""
