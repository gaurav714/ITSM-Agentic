$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root '..\backend\.venv\Scripts\python.exe'

Push-Location $Root
try {
    & $Python -m pip install -r requirements.txt
    & $Python -m pip install pyinstaller==6.11.1
    & $Python -m PyInstaller `
        --clean `
        --onefile `
        --name LocalDiagnosticAgent `
        --hidden-import app.main `
        --hidden-import app.agent `
        --hidden-import app.tools `
        --hidden-import app.schemas `
        --hidden-import app.mcp `
        --collect-submodules uvicorn `
        --collect-submodules fastapi `
        --collect-submodules starlette `
        run_agent.py

    Write-Host ''
    Write-Host 'Built executable:'
    Write-Host (Join-Path $Root 'dist\LocalDiagnosticAgent.exe')
}
finally {
    Pop-Location
}
