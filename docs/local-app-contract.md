# Local Diagnostic App Contract

The local diagnostic app is a separate app running on the user's machine.
The helpdesk browser UI calls it over localhost when the backend requests
browser diagnostics, then forwards the structured tool response to
`/diagnostics/browser`.

## Endpoint

Default URL used by the frontend:

```text
POST http://127.0.0.1:8765/local-app
```

Override with:

```text
VITE_LOCAL_APP_URL=http://127.0.0.1:8765/local-app
```

The local app must allow CORS from the frontend origin, for example
`http://localhost:5173`.

## Tool Discovery

The server supports local app JSON-RPC methods:

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "tools/list",
  "params": {}
}
```

Current tools:

- `diagnostics.search`
- `actions.stop_edge`
- `actions.collect_windows_update_status`
- `actions.open_windows_update_settings`
- `actions.run_powershell_task`

## Diagnostics Request

```json
{
  "jsonrpc": "2.0",
  "id": "diag-1",
  "method": "tools/call",
  "params": {
    "name": "diagnostics.search",
    "arguments": {
      "query": "system is slow",
      "context": {
        "session_id": "browser-session-id",
        "device_name": "UNKNOWN-PC",
        "diagnostic_id": "DIAG-1234ABCD",
        "browser_metrics": {
          "user_agent": "Mozilla/5.0 ...",
          "platform": "Win32",
          "cpu_cores": 8,
          "device_memory_gb": 16,
          "online": true,
          "connection_type": "4g",
          "page_load_ms": 1234
        }
      }
    }
  }
}
```

## Response

The browser stores `result.structuredContent` as
`metrics.local_app_response`. These top-level structured fields are also
normalized when present:

```json
{
  "jsonrpc": "2.0",
  "id": "diag-1",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "High memory pressure detected at 91%."
      }
    ],
    "structuredContent": {
      "summary": "High memory pressure detected at 91%.",
      "recommendation": "Close high-memory applications or restart the workstation; escalate if memory remains above 85%.",
      "tools": [
        {
          "name": "process_snapshot",
          "status": "complete",
          "description": "Collected top processes by memory usage."
        }
      ],
      "actions": [
        {
          "id": "stop_edge",
          "label": "Close Microsoft Edge",
          "description": "Stop Microsoft Edge browser processes running on this system.",
          "available": true
        }
      ],
      "metrics": {
        "cpu_pct": 42,
        "memory_pct": 91,
        "physical_cpu_cores": 4,
        "logical_cpu_cores": 8,
        "browser_hardware_concurrency": 8,
        "top_processes": ["msedge.exe", "Teams", "Chrome"],
        "edge_running": true
      }
    },
    "isError": false
  }
}
```

The browser treats the local app server as optional. If it is not running or
times out, the frontend still submits browser-only diagnostics with
`local_app_available: false`.

## Remediation Actions

The local app server exposes only allowlisted action tools. The browser calls an
action tool only after the backend asks for it and the user confirms.

Current action:

```text
actions.stop_edge
actions.collect_windows_update_status
actions.open_windows_update_settings
actions.run_powershell_task
```

Request:

```json
{
  "jsonrpc": "2.0",
  "id": "action-1",
  "method": "tools/call",
  "params": {
    "name": "actions.stop_edge",
    "arguments": {
      "action": "stop_edge",
      "context": {
        "session_id": "browser-session-id",
        "device_name": "Gaurav",
        "diagnostic_id": "DIAG-1234ABCD"
      }
    }
  }
}
```

Structured response:

```json
{
  "action": "stop_edge",
  "status": "complete",
  "message": "Stopped 2 Microsoft Edge process(es).",
  "stopped_processes": ["msedge.exe", "msedge.exe"],
  "errors": []
}
```

## Local System Agent PowerShell Tasks

The Local System Agent uses `actions.run_powershell_task` for generic local
system questions. The local app is only the executor: the backend plans the
task, the frontend asks the user for approval, and the backend interprets the
returned output.

Request:

```json
{
  "jsonrpc": "2.0",
  "id": "ps-1",
  "method": "tools/call",
  "params": {
    "name": "actions.run_powershell_task",
    "arguments": {
      "action": "run_powershell_task",
      "task_id": "LOCAL-1234ABCD",
      "command": "Get-PSDrive -Name C | Select-Object Name,Used,Free | ConvertTo-Json -Compress",
      "timeout_seconds": 10,
      "context": {
        "session_id": "browser-session-id",
        "device_name": "LOCAL-ENDPOINT"
      }
    }
  }
}
```

Structured response:

```json
{
  "action": "run_powershell_task",
  "task_id": "LOCAL-1234ABCD",
  "status": "complete",
  "message": "PowerShell task completed.",
  "stdout": "{\"Name\":\"C\",\"Used\":123,\"Free\":456}",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 240,
  "needs_elevation": false,
  "errors": []
}
```

Status values:

```text
complete
failed
timeout
rejected
needs_elevation
unsupported
```

The local app runs the command as the current user with `powershell
-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command <command>`. It
captures stdout, stderr, exit code, duration, and elevation-looking failures.
It does not attempt administrator elevation.

## Local Action Result Forwarding

After the frontend receives a local action result, it sends it to the backend:

```text
POST /diagnostics/local-action
```

For Local System Agent tasks, the payload includes both the execution result and
the backend-provided task context:

```json
{
  "session_id": "browser-session-id",
  "action": "run_powershell_task",
  "task_id": "LOCAL-1234ABCD",
  "status": "complete",
  "message": "PowerShell task completed.",
  "stdout": "{\"Name\":\"C\",\"FreeGB\":127.54,\"UsedGB\":348.39}",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 240,
  "needs_elevation": false,
  "errors": [],
  "task_context": {
    "user_request": "how much disk space is free on C drive?",
    "summary": "Check free and used disk space on C: drive.",
    "command": "Get-PSDrive -Name C ...",
    "expected_result": "JSON with used and free disk space in GB.",
    "interpretation_hint": "Explain free and used disk space in GB and mention the drive.",
    "risk_level": "low",
    "timeout_seconds": 10
  }
}
```

The backend stores this as `local_action_result` in the session and generates
the user-facing answer from the original request, task context, stdout/stderr,
exit code, and status. The frontend should not interpret PowerShell output for
the user.

## Windows Update Actions

The Windows Update workflow can ask the frontend to trigger one of these
allowlisted local app actions after explicit user approval:

```text
collect_windows_update_status
open_windows_update_settings
```

The frontend maps those workflow action ids to local app JSON-RPC action tools:

```text
collect_windows_update_status -> actions.collect_windows_update_status
open_windows_update_settings -> actions.open_windows_update_settings
```

### Collect Windows Update Status

Request:

```json
{
  "jsonrpc": "2.0",
  "id": "wu-status-1",
  "method": "tools/call",
  "params": {
    "name": "actions.collect_windows_update_status",
    "arguments": {
      "action": "collect_windows_update_status",
      "context": {
        "session_id": "browser-session-id",
        "device_name": "LOCAL-ENDPOINT"
      }
    }
  }
}
```

Structured response:

```json
{
  "action": "collect_windows_update_status",
  "status": "complete",
  "message": "Collected Windows Update service status.",
  "service_statuses": {
    "wuauserv": {
      "name": "wuauserv",
      "status": "running",
      "start_type": "manual"
    }
  },
  "pending_reboot": false,
  "errors": []
}
```

### Open Windows Update Settings

Request:

```json
{
  "jsonrpc": "2.0",
  "id": "wu-settings-1",
  "method": "tools/call",
  "params": {
    "name": "actions.open_windows_update_settings",
    "arguments": {
      "action": "open_windows_update_settings",
      "context": {
        "session_id": "browser-session-id",
        "device_name": "LOCAL-ENDPOINT"
      }
    }
  }
}
```

Structured response:

```json
{
  "action": "open_windows_update_settings",
  "status": "complete",
  "message": "Opened Windows Update settings.",
  "opened_uri": "ms-settings:windowsupdate",
  "errors": []
}
```

Local action execution is gated by backend workflow state. The LLM may select an
allowlisted action, but the workflow will not trigger it until the user has
explicitly approved local workstation access.

Generic PowerShell execution is also gated by backend workflow state and the
frontend approval modal. The command is displayed before execution. Commands run
only as the current local app user, have bounded timeouts and truncated output,
and return `needs_elevation` instead of trying to elevate.
