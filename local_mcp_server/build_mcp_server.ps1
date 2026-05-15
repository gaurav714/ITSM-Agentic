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
        --collect-submodules uvicorn `
        --collect-submodules fastapi `
        --collect-submodules starlette `
        --distpath dist_onedir `
        run_server.py

    Write-Host ''
    Write-Host 'Built MCP server executable bundle:'
    Write-Host (Join-Path $Root 'dist_onedir\LocalDiagnosticMcpServer\LocalDiagnosticMcpServer.exe')
}
finally {
    Pop-Location
}
