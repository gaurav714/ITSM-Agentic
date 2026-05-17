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
