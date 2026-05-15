# Local Diagnostic Assistant

This is the user-system companion app for the helpdesk browser UI. It runs on
the user's workstation, accepts browser requests over localhost, searches local
diagnostic tools for a "system is slow" request, runs safe read-only checks, and
returns normalized findings that the browser forwards to the backend.

## Run

Install local assistant dependencies:

```powershell
..\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`psutil` enables live CPU, memory, and process metrics. Without it, the agent
still returns browser metrics, disk space, and system profile information.

```powershell
cd local_diagnostic_agent
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

The frontend defaults to:

```text
http://127.0.0.1:8765/diagnostics/search
```

Override with `VITE_LOCAL_DIAGNOSTIC_AGENT_URL` if needed.

## Endpoint

```text
POST /diagnostics/search
```

The response includes:

- `summary`
- `recommendation`
- `tools`
- `actions`
- `metrics`

## Remediation Actions

The app exposes only allowlisted remediation actions. At the moment, the only
action is:

```text
POST /actions/stop-edge
```

It accepts `{"action": "stop_edge"}` and stops Microsoft Edge processes if they
are running. It does not execute arbitrary commands.
