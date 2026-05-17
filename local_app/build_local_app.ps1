$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '..\backend\.venv\Scripts\python.exe'

Push-Location $Root
try {
    & $Python -m pip install -r requirements.txt
    & $Python -m pip install pyinstaller==6.11.1
    & $Python -m PyInstaller `
        --clean `
        --noconfirm `
        --onedir `
        --name LocalDiagnosticApp `
        --hidden-import app.main `
        --hidden-import app.agent `
        --hidden-import app.tools `
        --hidden-import app.schemas `
        --hidden-import app.local_app `
        --hidden-import _socket `
        --hidden-import select `
        --hidden-import _overlapped `
        --collect-submodules uvicorn `
        --collect-submodules fastapi `
        --collect-submodules starlette `
        --distpath dist_onedir `
        run_server.py

    $BundleDir = Join-Path $Root 'dist_onedir\LocalDiagnosticApp'
    $BatPath = Join-Path $BundleDir 'start_local_app.bat'
    $PsPath = Join-Path $BundleDir 'start_local_app.ps1'
    $DiagPath = Join-Path $BundleDir 'diagnose_startup.bat'

    @'
@echo off
setlocal
cd /d "%~dp0"
if not exist "_internal\_socket.pyd" (
  echo Missing _internal\_socket.pyd.
  echo Extract the full LocalDiagnosticApp folder from the zip before running.
  echo Do not run only the exe, and do not run it from inside the zip preview.
  pause
  exit /b 1
)
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start_local_app.ps1"
'@ | Set-Content -LiteralPath $BatPath -Encoding ASCII

    @'
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$required = @(
    "LocalDiagnosticApp.exe",
    "_internal\_socket.pyd",
    "_internal\select.pyd",
    "_internal\_overlapped.pyd",
    "_internal\python311.dll"
)

foreach ($rel in $required) {
    $path = Join-Path $root $rel
    if (-not (Test-Path $path)) {
        Write-Host "Missing required bundled file: $rel" -ForegroundColor Red
        Write-Host "Extract the full LocalDiagnosticApp folder from the zip and run this script from inside that folder."
        Read-Host "Press Enter to close"
        exit 1
    }
}

Get-ChildItem -LiteralPath $root -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
& (Join-Path $root "LocalDiagnosticApp.exe") --host 127.0.0.1 --port 8765
'@ | Set-Content -LiteralPath $PsPath -Encoding ASCII

    @'
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
'@ | Set-Content -LiteralPath $DiagPath -Encoding ASCII

    Get-ChildItem -LiteralPath (Join-Path $Root 'dist_onedir') -Filter 'LocalDiagnosticApp*.zip' |
        Remove-Item -Force

    $ZipPath = Join-Path $Root 'dist_onedir\LocalDiagnosticApp.zip'
    Compress-Archive -Path $BundleDir -DestinationPath $ZipPath -Force

    $BuildDir = Join-Path $Root 'build'
    $SpecPath = Join-Path $Root 'LocalDiagnosticApp.spec'
    if (Test-Path $BuildDir) {
        Remove-Item -LiteralPath $BuildDir -Recurse -Force
    }
    if (Test-Path $SpecPath) {
        Remove-Item -LiteralPath $SpecPath -Force
    }

    Write-Host ''
    Write-Host 'Built local app executable bundle:'
    Write-Host (Join-Path $Root 'dist_onedir\LocalDiagnosticApp\LocalDiagnosticApp.exe')
    Write-Host 'Built local app zip:'
    Write-Host $ZipPath
}
finally {
    Pop-Location
}
