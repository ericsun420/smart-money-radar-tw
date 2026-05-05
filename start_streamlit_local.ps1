$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Test-Path $BundledPython) { $BundledPython } else { "python" }

Write-Host ""
Write-Host "Starting Smart Money Radar Streamlit viewer..."
Write-Host "Local URL: http://127.0.0.1:8501"
Write-Host ""

Set-Location $ProjectRoot
& $Python -m streamlit run streamlit_app.py --server.port 8501 --server.headless true

