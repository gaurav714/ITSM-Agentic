@echo off
setlocal
cd /d "%~dp0"
LocalDiagnosticMcpServer.exe --host 127.0.0.1 --port 8765
