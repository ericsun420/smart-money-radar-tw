@echo off
setlocal
cd /d "%~dp0backend"
set TOKEN_FILE=%~dp0backend\public_access_token.txt
if exist "%TOKEN_FILE%" (
  for /f "usebackq delims=" %%A in ("%TOKEN_FILE%") do set SMART_MONEY_ACCESS_TOKEN=%%A
)
"%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
