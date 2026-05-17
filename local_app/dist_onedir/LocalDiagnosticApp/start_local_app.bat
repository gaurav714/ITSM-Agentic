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
