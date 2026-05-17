# Project Status — AI Helpdesk Assistant Platform

_Last updated: 2026-05-16_

## Overview

A modular, conversational AI IT helpdesk platform. Iteration 1 focuses on the **System Slow Diagnostics** workflow end-to-end, with a generic frontend shell and backend architecture designed to host many workflows over time.

- **Backend:** Python 3, FastAPI, LangGraph, LangChain, Pydantic
- **Frontend:** React, Vite, TailwindCSS, React Query, Zustand, Axios
- **LLM:** OpenAI (`gpt-4o-mini` by default; configurable via `OPENAI_MODEL`)

---

## Current State — What Works Today

### Backend — implemented & tested

| Area                                                                | Status | Notes                                                                                 |
| ------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------- |
| FastAPI app + CORS                                                  | ✅     | [main.py](backend/app/main.py); 14 routes                                             |
| Workflow registry pattern                                           | ✅     | [workflow_registry.py](backend/app/services/workflow_registry.py)                     |
| `BaseWorkflow` abstract contract                                    | ✅     | [base.py](backend/app/workflows/base.py)                                              |
| New Employee Onboarding workflow                                    | ✅     | LangGraph tool-using agent, duplicate check, mock identity DB, RBAC groups, MFA, welcome email |
| Windows Update Failure workflow                                     | ✅     | LangGraph + LLM-assisted follow-up interpretation, guided fixes first, local access approval gate, local app action to open Windows Update settings |
| In-memory session store                                             | ✅     | [session_store.py](backend/app/memory/session_store.py) — replace with Redis/DB later |
| Diagnostic router (priority: Intune → SCCM → Browser + local app)   | ✅     | [diagnostic_router.py](backend/app/services/diagnostic_router.py)                     |
| Mock Intune adapter                                                 | ✅     | `LAPTOP-INTUNE-01`                                                                    |
| Mock SCCM adapter                                                   | ✅     | `DESKTOP-SCCM-42`                                                                     |
| Browser diagnostics adapter                                         | ✅     | Real metrics pushed from frontend                                                     |
| Mock ticketing adapter                                              | ✅     | Returns `INC########` ids                                                             |
| Conversation agent / message router                                 | ✅     | [conversation_agent.py](backend/app/agents/conversation_agent.py)                     |
| Browser → local diagnostic app → backend handoff             | ✅     | Browser can call a user-system local app and submit its structured response with diagnostics |
| Local diagnostic app scaffold                                | ✅     | [local_app](local_app) exposes localhost `/local-app` with `tools/list` and `tools/call` |
| Local remediation action handoff                                    | ✅     | User can approve the local app server to stop Microsoft Edge before ticket creation    |

### Backend — **Agentic** capabilities (LLM-active when `OPENAI_API_KEY` is set)

| Capability                                                | Status | Implementation                                                                           |
| --------------------------------------------------------- | ------ | ---------------------------------------------------------------------------------------- |
| LLM intent classification (free-text → workflow id)       | ✅     | [intent_router.py](backend/app/agents/intent_router.py)                                  |
| LLM device-name extraction (structured output)            | ✅     | `_extract_device_name` in [workflow.py](backend/app/workflows/system_slow/workflow.py)   |
| LLM yes/no confirmation classification                    | ✅     | `_classify_confirmation` in [workflow.py](backend/app/workflows/system_slow/workflow.py) |
| LLM-generated diagnostic summary                          | ✅     | `_summarize` in [workflow.py](backend/app/workflows/system_slow/workflow.py)             |
| LLM-generated ticket draft (title, description, priority) | ✅     | [ticket_service.py](backend/app/services/ticket_service.py)                              |
| Shared LLM client + structured-output helper              | ✅     | [llm.py](backend/app/services/llm.py)                                                    |
| Deterministic fallback for every LLM call                 | ✅     | Works without API key                                                                    |
| Local app telemetry ingestion                             | ✅     | Browser-submitted local app output is normalized, summarized, and used before ticketing |

### Backend — REST endpoints (all working)

- `GET /health`
- `GET /workflows`
- `POST /agent/message`
- `POST /agent/start_workflow`
- `POST /diagnostics/start`
- `GET /diagnostics/{id}`
- `POST /diagnostics/browser`
- `POST /tickets/draft`
- `POST /tickets/create`
- `GET /tickets`

### Frontend — implemented

| Area                                                   | Status |
| ------------------------------------------------------ | ------ |
| Layout: Header / Sidebar / Main                        | ✅     |
| Pages: Home, Conversation, Tickets, Settings           | ✅     |
| Chat UI with streaming-style card interleaving         | ✅     |
| Generic card renderer (workflow-aware)                 | ✅     |
| Browser diagnostics auto-collection on backend trigger | ✅     |
| React Query data fetching                              | ✅     |
| Zustand session store                                  | ✅     |
| Sidebar pulled live from `/workflows`                  | ✅     |

### Active workflows in the registry

| id                        | Title                   | Active         |
| ------------------------- | ----------------------- | -------------- |
| `system_slow_diagnostics` | System Slow Diagnostics | ✅             |
| `new_employee_onboarding` | New Employee Onboarding | ✅             |
| `windows_update_failure`  | Windows Update Failure  | ✅             |
| `password_reset`          | Password Reset          | ⏳ Coming soon |
| `vpn_access`              | VPN Access Request      | ⏳ Coming soon |
| `software_install`        | Software Installation   | ⏳ Coming soon |
| `account_unlock`          | Account Unlock          | ⏳ Coming soon |
| `ticket_status`           | Ticket Status Lookup    | ⏳ Coming soon |
| `application_outage`      | Application Outage      | ⏳ Coming soon |

> **Removed from scope:** `deployment_request` and `kubernetes_issue` (no longer registered).

### Security guardrails in place

- LLM never executes commands or shell.
- Adapters are an explicit allowlist; no dynamic dispatch.
- Device names validated by regex (`^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$`) **after** LLM extraction, blocking prompt-injection payloads.
- Tickets only created after the deterministic confirmation gate — the LLM cannot trigger ticket creation directly.
- API keys live only in backend `.env`; never exposed to the frontend.
- CORS restricted to configured origins.

---

## Pending — Not Yet Implemented

### Agentic upgrades (next high-value steps)

| #   | Item                                                                                                                                                                                                                     | Why it matters                                                       |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| 1   | **Real LangGraph execution path** — current `StateGraph` nodes are pass-throughs; `handle()` is a hand-coded ladder. Move logic into nodes with conditional edges driven by session state.                               | Enables tracing, replay, and easier branching for future workflows.  |
| 2   | **LangGraph checkpointer** (e.g. `MemorySaver` / SQLite) keyed by `session_id`.                                                                                                                                          | Replaces the custom in-memory dict store; adds replay & persistence. |
| 3   | **Package/install the user-system local app** — create installer/service packaging, startup policy, auth token/CORS hardening, and signed distribution for the workstation app. | The scaffold exists; packaging and hardening make it deployable beyond local development. |
| 4   | **Multi-turn conversation memory** with rolling summary.                                                                                                                                                                 | Long sessions don't blow the context window.                         |
| 5   | **Streaming responses** (SSE) from `/agent/message`.                                                                                                                                                                     | Token-level UX in the chat.                                          |
| 6   | **LangSmith tracing** (`LANGCHAIN_TRACING_V2=true`).                                                                                                                                                                     | Observability for every LLM/tool call.                               |
| 7   | **Confidence-driven clarification** in intent router — if LLM confidence is low, ask a clarifying question instead of dumping the workflow list.                                                                         | Better UX for vague requests.                                        |

### Workflows still to build

| Workflow              | Notes                                                                                    |
| --------------------- | ---------------------------------------------------------------------------------------- |
| Password Reset        | Likely the simplest — LLM extracts username, calls mock identity adapter, raises ticket. |
| VPN Access Request    | Form-style intake → approval workflow → ticket.                                          |
| Software Installation | Catalog lookup + license check + ticket.                                                 |
| Account Unlock        | Identity adapter call.                                                                   |
| Ticket Status Lookup  | Read-only against `mock_ticket_adapter`; good first multi-turn test of the registry.     |
| Application Outage    | Aggregate reports, dedupe by app id, notify on-call.                                     |

### Adapter integrations (mocked → real)

| Iteration | Item                                                                       |
| --------- | -------------------------------------------------------------------------- |
| 2         | **Real Intune** via Microsoft Graph (`DeviceManagement.Read.All`, etc.).   |
| 3         | **Real SCCM/MECM** via WMI / SCCM SDK / approved scripts.                  |
| 4         | **Hardened local app server deployment** — installer/service + auth + signed distribution. |
| 5         | **Real ServiceNow / Jira** ticketing — replace `mock_ticket_adapter`.      |

### Platform hardening (non-LLM)

- Persistent session storage (Redis or Postgres) instead of in-memory dict.
- AuthN/AuthZ — currently no user identity; assumes trusted callers.
- Rate limiting on `/agent/message`.
- Request/response logging with PII redaction.
- Unit + integration tests (pytest); current coverage is ad-hoc PowerShell smoke scripts ([tests_smoke.ps1](backend/tests_smoke.ps1), [tests_smoke2.ps1](backend/tests_smoke2.ps1), [tests_agentic.ps1](backend/tests_agentic.ps1)).
- CI pipeline (GitHub Actions) — lint, type-check, test, build.
- Containerization (Dockerfile + docker-compose for backend + frontend).

### Frontend polish

- Confirmation modal on ticket creation (component exists, not wired in).
- Conversation history sidebar / per-session navigation.
- Error toasts (currently silent on API failure inside conversation).
- Empty / loading states for the Tickets page.
- Markdown rendering in assistant messages (LLM occasionally emits markdown).
- Mobile layout (sidebar is hidden on small screens — no replacement nav).

---

## Acceptance Criteria — iteration 1

| Criterion                                                            | Status                                                  |
| -------------------------------------------------------------------- | ------------------------------------------------------- |
| Frontend shows multiple workflow options                             | ✅                                                      |
| Only System Slow workflow is active                                  | ✅                                                      |
| User can type "My system is slow"                                    | ✅                                                      |
| Assistant triggers local app diagnostics without asking device name       | ✅                                                   |
| Diagnostic router selects method                                     | ✅                                                      |
| Browser diagnostics work as fallback                                 | ✅                                                      |
| Diagnostic results are summarized                                    | ✅ (LLM when key set; deterministic fallback otherwise) |
| Ticket draft is generated                                            | ✅ (LLM when key set)                                   |
| User can confirm ticket creation                                     | ✅ (LLM-classified confirmation)                        |
| Mock ticket number is returned                                       | ✅                                                      |
| Architecture supports adding future workflows without major rewrites | ✅                                                      |

**Iteration 1 is complete.** Several agentic upgrades from step 1 of the original plan have already been delivered ahead of schedule.

---

## How to run

```powershell
# Backend
cd backend
.\.venv\Scripts\Activate.ps1   # (already created)
uvicorn app.main:app --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev
```

App: <http://localhost:5173> · API: <http://localhost:8000/docs>
