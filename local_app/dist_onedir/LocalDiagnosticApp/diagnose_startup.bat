@echo off
setlocal
cd /d "%~dp0"
set LOG=%~dp0local_app_startup.log
echo Local app startup diagnostics > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo Folder: %CD% >> "%LOG%"
echo. >> "%LOG%"

echo Required files: >> "%LOG%"
if exist "LocalDiagnosticApp.exe" (echo OK LocalDiagnosticApp.exe >> "%LOG%") else (echo MISSING LocalDiagnosticApp.exe >> "%LOG%")
if exist "_internal\_socket.pyd" (echo OK _internal\_socket.pyd >> "%LOG%") else (echo MISSING _internal\_socket.pyd >> "%LOG%")
if exist "_internal\select.pyd" (echo OK _internal\select.pyd >> "%LOG%") else (echo MISSING _internal\select.pyd >> "%LOG%")
if exist "_internal\_overlapped.pyd" (echo OK _internal\_overlapped.pyd >> "%LOG%") else (echo MISSING _internal\_overlapped.pyd >> "%LOG%")
if exist "_internal\python311.dll" (echo OK _internal\python311.dll >> "%LOG%") else (echo MISSING _internal\python311.dll >> "%LOG%")
echo. >> "%LOG%"

echo Unblocking downloaded files... >> "%LOG%"
powershell -ExecutionPolicy Bypass -NoProfile -Command "Get-ChildItem -LiteralPath '%~dp0' -Recurse -File | Unblock-File -ErrorAction SilentlyContinue" >> "%LOG%" 2>&1

echo Starting server... >> "%LOG%"
start "LocalDiagnosticApp" "%~dp0LocalDiagnosticApp.exe" --host 127.0.0.1 --port 8765
timeout /t 5 /nobreak > nul

echo. >> "%LOG%"
echo Testing local app endpoint... >> "%LOG%"
powershell -ExecutionPolicy Bypass -NoProfile -Command "try { Invoke-RestMethod -Method Post http://127.0.0.1:8765/local-app -ContentType 'application/json' -Body '{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"tools/list\",\"params\":{}}' | ConvertTo-Json -Depth 8 } catch { $_ | Out-String }" >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo Diagnostics written to:
echo %LOG%
type "%LOG%"
pause
