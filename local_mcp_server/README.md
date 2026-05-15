# Local Diagnostic MCP Server

This is the user-system companion app for the helpdesk browser UI. It runs on
the user's workstation as a local MCP server, accepts MCP JSON-RPC requests over
localhost, exposes allowlisted diagnostic tools, and returns normalized findings
that the browser forwards to the backend.

## Run

Install local MCP server dependencies:

```powershell
..\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`psutil` enables live CPU, memory, and process metrics. Without it, the MCP server
still returns browser metrics, disk space, and system profile information.

```powershell
cd local_mcp_server
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

The frontend defaults to:

```text
http://127.0.0.1:8765/mcp
```

Override with `VITE_LOCAL_MCP_SERVER_URL` if needed.

## MCP Endpoint

```text
POST /mcp
```

Supported MCP methods:

- `initialize`
- `tools/list`
- `tools/call`

Current tools:

- `diagnostics.search`
- `actions.stop_edge`

The `diagnostics.search` structured tool result includes `summary`,
`recommendation`, `tools`, `actions`, and `metrics`.

## Remediation Actions

The app exposes only allowlisted remediation actions as MCP tools. At the
moment, the only action tool is:

```text
actions.stop_edge
```

It accepts `{"action": "stop_edge"}` and stops Microsoft Edge processes if they
are running. It does not execute arbitrary commands.

## Build Windows EXE

From this folder:

```powershell
.\build_mcp_server.ps1
```

The executable bundle is created at:

```text
dist_onedir\LocalDiagnosticMcpServer\LocalDiagnosticMcpServer.exe
```

Run it on the user's machine:

```powershell
.\LocalDiagnosticMcpServer.exe
```

Optional:

```powershell
.\LocalDiagnosticMcpServer.exe --port 8765 --open-health
```
