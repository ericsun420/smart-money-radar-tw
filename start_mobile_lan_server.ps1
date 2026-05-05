$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }

$LanIps = (ipconfig | Select-String -Pattern "IPv4.*?:\s*([0-9.]+)").Matches |
  ForEach-Object { $_.Groups[1].Value } |
  Where-Object { $_ -notlike "127.*" -and $_ -notlike "169.254.*" } |
  Select-Object -Unique

Write-Host ""
Write-Host "Smart Money Radar 台股即時資金雷達 App 第一版基準"
Write-Host "啟動手機區網瀏覽模式..."
Write-Host ""
Write-Host "本機網址： http://127.0.0.1:8000/"
foreach ($ip in $LanIps) {
  Write-Host "手機同 Wi-Fi 可試： http://$ip`:8000/"
}
Write-Host ""
Write-Host "若手機無法連線，通常是 Windows 防火牆尚未允許 Python/Uvicorn 接收區網連線。"
Write-Host ""

Set-Location $BackendRoot
& $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
