# Local Diagnostic MCP Server Contract

The local diagnostic MCP server is a separate app running on the user's machine.
The helpdesk browser UI calls it over localhost when the backend requests
browser diagnostics, then forwards the structured tool response to
`/diagnostics/browser`.

## Endpoint

Default URL used by the frontend:

```text
POST http://127.0.0.1:8765/mcp
```

Override with:

```text
VITE_LOCAL_DIAGNOSTIC_AGENT_URL=http://127.0.0.1:8765/mcp
```

The local app must allow CORS from the frontend origin, for example
`http://localhost:5173`.

## Tool Discovery

The server supports MCP-style JSON-RPC methods:

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
`metrics.local_agent_response`. These top-level structured fields are also
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
        "top_processes": ["msedge.exe", "Teams", "Chrome"],
        "edge_running": true
      }
    },
    "isError": false
  }
}
```

The browser treats the local MCP server as optional. If it is not running or
times out, the frontend still submits browser-only diagnostics with
`local_agent_available: false`.

## Remediation Actions

The local MCP server exposes only allowlisted action tools. The browser calls an
action tool only after the backend asks for it and the user confirms.

Current action:

```text
actions.stop_edge
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
