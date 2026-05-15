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
        --name LocalDiagnosticMcpServer `
        --hidden-import app.main `
        --hidden-import app.agent `
        --hidden-import app.tools `
        --hidden-import app.schemas `
        --hidden-import app.mcp `
        --hidden-import _socket `
        --hidden-import select `
        --hidden-import _overlapped `
        --collect-submodules uvicorn `
        --collect-submodules fastapi `
        --collect-submodules starlette `
        --distpath dist_onedir `
        run_server.py

    $BundleDir = Join-Path $Root 'dist_onedir\LocalDiagnosticMcpServer'
    $BatPath = Join-Path $BundleDir 'start_local_mcp_server.bat'
    $PsPath = Join-Path $BundleDir 'start_local_mcp_server.ps1'

    @'
@echo off
setlocal
cd /d "%~dp0"
if not exist "_internal\_socket.pyd" (
  echo Missing _internal\_socket.pyd.
  echo Extract the full LocalDiagnosticMcpServer folder from the zip before running.
  echo Do not run only the exe, and do not run it from inside the zip preview.
  pause
  exit /b 1
)
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start_local_mcp_server.ps1"
'@ | Set-Content -LiteralPath $BatPath -Encoding ASCII

    @'
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$required = @(
    "LocalDiagnosticMcpServer.exe",
    "_internal\_socket.pyd",
    "_internal\select.pyd",
    "_internal\_overlapped.pyd",
    "_internal\python311.dll"
)

foreach ($rel in $required) {
    $path = Join-Path $root $rel
    if (-not (Test-Path $path)) {
        Write-Host "Missing required bundled file: $rel" -ForegroundColor Red
        Write-Host "Extract the full LocalDiagnosticMcpServer folder from the zip and run this script from inside that folder."
        Read-Host "Press Enter to close"
        exit 1
    }
}

Get-ChildItem -LiteralPath $root -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
& (Join-Path $root "LocalDiagnosticMcpServer.exe") --host 127.0.0.1 --port 8765
'@ | Set-Content -LiteralPath $PsPath -Encoding ASCII

    Write-Host ''
    Write-Host 'Built MCP server executable bundle:'
    Write-Host (Join-Path $Root 'dist_onedir\LocalDiagnosticMcpServer\LocalDiagnosticMcpServer.exe')
}
finally {
    Pop-Location
}
