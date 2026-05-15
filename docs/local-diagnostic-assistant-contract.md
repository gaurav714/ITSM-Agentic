# Local Diagnostic Assistant Contract

The local diagnostic assistant is a separate app running on the user's machine.
The helpdesk browser UI calls it over localhost when the backend requests
browser diagnostics, then forwards the response to `/diagnostics/browser`.

## Endpoint

Default URL used by the frontend:

```text
POST http://127.0.0.1:8765/diagnostics/search
```

Override with:

```text
VITE_LOCAL_DIAGNOSTIC_AGENT_URL=http://127.0.0.1:8765/diagnostics/search
```

The local app must allow CORS from the frontend origin, for example
`http://localhost:5173`.

## Request

```json
{
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
```

## Response

The backend preserves the full JSON in `metrics.local_agent_response`. These
top-level fields are also normalized when present:

```json
{
  "summary": "High memory pressure detected; Teams and browser tabs are the largest consumers.",
  "recommendation": "Close unused browser tabs and restart Teams; escalate if memory remains above 85%.",
  "tools": [
    {
      "name": "process_snapshot",
      "status": "complete",
      "description": "Collected top process memory and CPU usage."
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
    "top_processes": ["msedge.exe", "Teams", "Chrome"],
    "edge_running": true
  }
}
```

The browser treats the local assistant as optional. If it is not running or
times out, the frontend still submits browser-only diagnostics with
`local_agent_available: false`.

## Remediation Actions

The local assistant exposes only allowlisted actions. The browser calls an
action endpoint only after the backend asks for it and the user confirms.

Current action:

```text
POST http://127.0.0.1:8765/actions/stop-edge
```

Request:

```json
{
  "action": "stop_edge",
  "context": {
    "session_id": "browser-session-id",
    "device_name": "Gaurav",
    "diagnostic_id": "DIAG-1234ABCD"
  }
}
```

Response:

```json
{
  "action": "stop_edge",
  "status": "complete",
  "message": "Stopped 2 Microsoft Edge process(es).",
  "stopped_processes": ["msedge.exe", "msedge.exe"],
  "errors": []
}
```
