# Local Diagnostic App

This is the user-system companion app for the helpdesk browser UI. It runs on
the user's workstation as a local app, accepts JSON-RPC requests over
localhost, exposes allowlisted diagnostic tools, and returns normalized findings
that the browser forwards to the backend.

## Run From Source

Install local app dependencies:

```powershell
..\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`psutil` enables live CPU, memory, and process metrics. Without it, the local app
still returns browser metrics, disk space, and system profile information.

```powershell
cd local_app
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

The frontend defaults to:

```text
http://127.0.0.1:8765/local-app
```

Override with `VITE_LOCAL_APP_URL` if needed.

## Local App Endpoint

```text
POST /local-app
```

Supported methods:

- `initialize`
- `tools/list`
- `tools/call`

Current tools:

- `diagnostics.search`
- `actions.stop_edge`
- `actions.collect_windows_update_status`
- `actions.open_windows_update_settings`
- `actions.run_powershell_task`

The `diagnostics.search` structured tool result includes `summary`,
`recommendation`, `tools`, `actions`, and `metrics`.

## Exposed Local App Tools

### `diagnostics.search`

Runs allowlisted local diagnostics for the user's workstation.

Input:

```json
{
  "query": "system is slow",
  "context": {
    "session_id": "browser-session-id",
    "device_name": "LOCAL-ENDPOINT",
    "diagnostic_id": "DIAG-1234ABCD",
    "browser_metrics": {}
  }
}
```

Internal checks used by this tool:

- `system_profile` — hostname, OS, machine type, CPU cores, browser-provided memory hint
- `disk_snapshot` — free and total space for the system drive
- `cpu_memory_snapshot` — current CPU and memory utilization through `psutil`
- `process_snapshot` — top memory processes and whether Microsoft Edge is running

Structured output includes:

- `summary`
- `recommendation`
- `tools`
- `actions`
- `metrics`
- `confidence`

Common metrics:

- `hostname`
- `os`
- `machine`
- `cpu_cores`
- `device_memory_gb`
- `disk_free_gb`
- `disk_total_gb`
- `cpu_pct`
- `memory_pct`
- `top_processes`
- `edge_running`

### `actions.stop_edge`

Stops Microsoft Edge processes after explicit user approval from the helpdesk UI.

Input:

```json
{
  "action": "stop_edge",
  "context": {
    "session_id": "browser-session-id",
    "device_name": "LOCAL-ENDPOINT",
    "diagnostic_id": "DIAG-1234ABCD"
  }
}
```

Structured output includes:

- `action`
- `status`
- `message`
- `stopped_processes`
- `errors`

This tool is allowlisted and does not execute arbitrary commands.

### `actions.collect_windows_update_status`

Collects Windows Update related service status and pending reboot state after
explicit user approval from the helpdesk UI.

Input:

```json
{
  "action": "collect_windows_update_status",
  "context": {
    "session_id": "browser-session-id",
    "device_name": "LOCAL-ENDPOINT"
  }
}
```

Structured output includes:

- `action`
- `status`
- `message`
- `service_statuses`
- `pending_reboot`
- `errors`

### `actions.open_windows_update_settings`

Opens the Windows Update Settings page after explicit user approval from the
helpdesk UI.

Input:

```json
{
  "action": "open_windows_update_settings",
  "context": {
    "session_id": "browser-session-id",
    "device_name": "LOCAL-ENDPOINT"
  }
}
```

Structured output includes:

- `action`
- `status`
- `message`
- `opened_uri`
- `errors`

### `actions.run_powershell_task`

Runs a backend-planned, user-approved PowerShell command as the current Windows
user. This tool is used by the Local System Agent. The local app does not plan
commands or interpret the result for the user; it only executes the approved
command and returns structured execution data to the browser, which forwards it
to the backend.

Input:

```json
{
  "action": "run_powershell_task",
  "task_id": "LOCAL-1234ABCD",
  "command": "Get-Date | Select-Object DateTime | ConvertTo-Json -Compress",
  "timeout_seconds": 10,
  "context": {
    "session_id": "browser-session-id",
    "device_name": "LOCAL-ENDPOINT"
  }
}
```

Structured output includes:

- `action`
- `task_id`
- `status`
- `message`
- `stdout`
- `stderr`
- `exit_code`
- `duration_ms`
- `needs_elevation`
- `errors`

Status values include `complete`, `failed`, `timeout`, `rejected`,
`needs_elevation`, and `unsupported`.

Example JSON-RPC request:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8765/local-app `
  -ContentType 'application/json' `
  -Body '{"jsonrpc":"2.0","id":"ps-1","method":"tools/call","params":{"name":"actions.run_powershell_task","arguments":{"action":"run_powershell_task","task_id":"LOCAL-DEMO","command":"Get-Date | Select-Object DateTime | ConvertTo-Json -Compress","timeout_seconds":10,"context":{"session_id":"demo","device_name":"LOCAL-ENDPOINT"}}}}'
```

## Remediation Actions

The app exposes only allowlisted remediation actions as local app tools. At the
moment, the action tools are:

```text
actions.stop_edge
actions.collect_windows_update_status
actions.open_windows_update_settings
actions.run_powershell_task
```

The first three are workflow-specific allowlisted actions. The
`actions.run_powershell_task` tool is generic, but it should only be called
after the backend has planned a task and the frontend has shown the user the
command for approval.

PowerShell tasks run as the current user, do not attempt elevation, have a
bounded timeout, and return captured stdout/stderr instead of displaying output
directly in the UI.

## Build Windows EXE

From this folder:

```powershell
.\build_local_app.ps1
```

The executable bundle is created at:

```text
dist_onedir\LocalDiagnosticApp\LocalDiagnosticApp.exe
```

The zip package is created at:

```text
dist_onedir\LocalDiagnosticApp.zip
```

## Important Packaging Note

This is a PyInstaller `onedir` build. The exe is not standalone by itself.
It must stay beside the bundled `_internal` folder:

```text
LocalDiagnosticApp\
  LocalDiagnosticApp.exe
  _internal\
    python311.dll
    _socket.pyd
    select.pyd
    _overlapped.pyd
    VCRUNTIME140.dll
    ...
```

Do not copy only `LocalDiagnosticApp.exe` to another location. It will fail
with errors such as `_socket module not found` because the native Python modules
live under `_internal`.

The deployable unit is the whole `LocalDiagnosticApp` folder, or the
`LocalDiagnosticApp.zip` file that contains that folder.

## Run On A Client Machine

1. Copy `dist_onedir\LocalDiagnosticApp.zip` to the client machine.
2. Extract the zip fully. Do not run from the zip preview.
3. Open the extracted `LocalDiagnosticApp` folder.
4. Run one of:

```bat
start_local_app.bat
```

or:

```powershell
.\LocalDiagnosticApp.exe
```

Optional:

```powershell
.\LocalDiagnosticApp.exe --port 8765 --open-health
```

Keep the server running while using the helpdesk browser UI. The frontend calls:

```text
http://127.0.0.1:8765/local-app
```

## Verify The Server

After starting the server, run:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8765/local-app `
  -ContentType 'application/json' `
  -Body '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

Expected tools:

```text
diagnostics.search
actions.stop_edge
actions.collect_windows_update_status
actions.open_windows_update_settings
actions.run_powershell_task
```

You can also run:

```bat
diagnose_startup.bat
```

This checks required bundled files, unblocks downloaded files, starts the server,
and writes `local_app_startup.log`.

## Findings From Packaging Tests

- The `onefile` build was rejected for now because it failed on some Windows
  machines while extracting `VCRUNTIME140.dll`.
- The working build is `onedir`, which avoids runtime self-extraction but
  requires the full folder to remain intact.
- If `_internal\_socket.pyd` is present but the exe still reports `_socket`
  errors, the usual causes are running only the exe, running from inside the zip
  preview, incomplete extraction, or Windows/AV blocking downloaded files.
- `start_local_app.bat` and `diagnose_startup.bat` call `Unblock-File`
  before launching to reduce downloaded-file blocking issues.
- The final package should be distributed as `LocalDiagnosticApp.zip`, not
  as a bare exe.
