# Project Status - AI Helpdesk Assistant Platform

_Last updated: 2026-06-11_

## Overview

A modular, conversational AI IT helpdesk platform with a FastAPI backend,
React/Vite frontend, and localhost companion app for workstation diagnostics.
The active workflows are **Local System Agent**, **System Slow Diagnostics**,
**New Employee Onboarding**, and **Windows Update Failure**.

- **Backend:** Python 3, FastAPI, LangGraph, LangChain, Pydantic
- **Frontend:** React, Vite, TailwindCSS, React Query, Zustand, Axios
- **LLM:** OpenAI (`gpt-4o-mini` by default; configurable with `OPENAI_MODEL`)

---

## Current State

### Backend

| Area | Status | Notes |
| --- | --- | --- |
| FastAPI app + CORS | Complete | `/health`, workflow, diagnostics, ticket, and local-action endpoints |
| Workflow registry pattern | Complete | `local_system_agent`, `system_slow_diagnostics`, `new_employee_onboarding`, `windows_update_failure`, plus placeholders |
| Conversation router | Complete | Sticky workflow routing and protocol-message protection for local/browser handoffs |
| Local System Agent | Complete | Backend plans approval-gated current-user PowerShell tasks and interprets returned output |
| System Slow Diagnostics | Complete | Uses browser diagnostics plus local app `diagnostics.search`; does not use generic PowerShell |
| New Employee Onboarding | Complete | LangGraph tool-using agent with mock identity operations |
| Windows Update Failure | Complete | Agentic decision loop with approval-gated allowlisted Windows Update local actions |
| Browser/local app handoff | Complete | Browser can call localhost local app and forward structured results to backend |
| Generic local action result ingestion | Complete | `/diagnostics/local-action` stores local action results, including `task_context` |
| Mock ticketing adapter | Complete | Returns mock `INC########` ticket ids |

### Local System Agent

The `local_system_agent` workflow handles direct workstation/system questions
and local tasks.

- Backend produces a local execution request with `task_id`, summary, risk
  level, command, timeout, expected result, and interpretation context.
- Frontend shows a highlighted permission modal before calling the local app.
- Local app runs `actions.run_powershell_task` as the current user with
  `-NoProfile`, timeout bounds, stdout/stderr capture, exit code, and
  `needs_elevation` detection.
- Frontend submits the execution result plus the original `task_context` to
  `/diagnostics/local-action`.
- Backend summarizes the returned output for the user. Simple facts such as
  disk space, time, timezone, hostname, current user, DOTA2 installed checks,
  and microphone availability have deterministic plans and direct answers.
- Planner validation rejects display-only formatting, overly large commands,
  metadata-only stdout schemas, and broad uncapped commands.

Safety limits:

- Every PowerShell task is explicit-workflow only and requires UI approval.
- Commands run as the current local app user.
- No administrator elevation is attempted.
- Timeout and output truncation protect the UI and backend.

### Local App Tools

Current JSON-RPC tools exposed at `http://127.0.0.1:8765/local-app`:

```text
diagnostics.search
actions.stop_edge
actions.collect_windows_update_status
actions.open_windows_update_settings
actions.run_powershell_task
```

`diagnostics.search` remains the System Slow path. `actions.run_powershell_task`
is reserved for backend-requested Local System Agent tasks.

### Frontend

| Area | Status |
| --- | --- |
| Header/sidebar/main layout | Complete |
| Conversation, Tickets, and Settings pages | Complete |
| Workflow navigation visible from chat routes | Complete |
| Fallback workflow links if `/workflows` fails | Complete |
| Browser diagnostics auto-collection on backend trigger | Complete |
| Generic local app action execution | Complete |
| Highlighted local permission modal | Complete |
| Backend URL/status-aware error messages | Complete |
| React Query data fetching and Zustand session store | Complete |

### Active Workflows

| id | Title | Active |
| --- | --- | --- |
| `local_system_agent` | Local System Agent | Yes |
| `system_slow_diagnostics` | System Slow Diagnostics | Yes |
| `new_employee_onboarding` | New Employee Onboarding | Yes |
| `windows_update_failure` | Windows Update Failure | Yes |
| `password_reset` | Password Reset | Coming soon |
| `vpn_access` | VPN Access Request | Coming soon |
| `software_install` | Software Installation | Coming soon |
| `account_unlock` | Account Unlock | Coming soon |
| `ticket_status` | Ticket Status Lookup | Coming soon |
| `application_outage` | Application Outage | Coming soon |

---

## Security Guardrails

- The LLM never directly executes commands.
- Backend-generated Local System Agent commands are shown to the user before
  the browser calls the local app.
- Generic PowerShell runs only as the current user and reports
  `needs_elevation` instead of elevating.
- System Slow and Windows Update use dedicated allowlisted local tools.
- Ticket creation still requires user confirmation.
- API keys live only in backend `.env`; they are never exposed to the frontend.
- CORS is controlled by configured origins and optional origin regex.

---

## Pending Work

### Platform hardening

- Persistent session storage instead of the in-memory session store.
- Authentication and authorization.
- Rate limiting on `/agent/message`.
- Request/response logging with PII redaction.
- Unit and integration test suite in CI.
- Containerization for backend and frontend.

### Local app deployment

- Installer/service packaging.
- Auth token or stronger localhost caller validation.
- Signed distribution and startup policy.

### Future integrations

| Iteration | Item |
| --- | --- |
| 2 | Real Intune via Microsoft Graph |
| 3 | Real SCCM/MECM integration |
| 4 | Hardened local app deployment |
| 5 | Real ServiceNow/Jira ticketing |

### Workflows still to build

- Password Reset
- VPN Access Request
- Software Installation
- Account Unlock
- Ticket Status Lookup
- Application Outage

---

## How To Run

```powershell
# Backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm run dev

# Local app
cd local_app
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

App: <http://localhost:5173>
API docs: <http://localhost:8000/docs>
Local app: <http://127.0.0.1:8765/local-app>

For LAN browser access, run the backend with `--host 0.0.0.0`, set
`VITE_API_BASE_URL` to the backend LAN URL, and configure backend CORS through
`ALLOWED_ORIGINS` or `ALLOWED_ORIGIN_REGEX`.
