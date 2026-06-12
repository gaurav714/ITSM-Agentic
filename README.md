# AI Helpdesk Assistant Platform

Generic AI-powered IT helpdesk assistant with a modular workflow registry. The active workflows include **Local System Agent**, **System Slow Diagnostics**, **New Employee Onboarding**, and **Windows Update Failure**.

The **Local System Agent** lets the backend plan approval-gated, current-user PowerShell tasks, the browser bridge asks the localhost app to execute them, and the backend interprets the returned structured output for the user. **System Slow Diagnostics** still uses the dedicated `diagnostics.search` local app tool for browser/workstation metrics. **Windows Update Failure** still uses allowlisted local app actions for Windows Update troubleshooting.

## Project Layout

```text
backend/    FastAPI + LangGraph + LangChain
frontend/   React + Vite + Tailwind + React Query + Zustand + Axios
local_app/  Local JSON-RPC app with allowlisted workstation diagnostics/actions
```

## Backend - Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # optional for most workflows, required for agentic Windows Update
uvicorn app.main:app --reload --port 8000
```

Health check: <http://localhost:8000/health>
OpenAPI docs: <http://localhost:8000/docs>

LLM keys are optional for most platform behavior. Without `OPENAI_API_KEY`, the intent router falls back to a deterministic keyword classifier. The Local System Agent has deterministic read-only plans for common facts such as disk space, time, hostname, current user, microphone availability, and selected installed-app checks. Broader Local System Agent requests require backend LLM planning. The Windows Update agentic decision loop requires a configured LLM unless `WINDOWS_UPDATE_ALLOW_DETERMINISTIC_FALLBACK=true` is explicitly enabled for demo/testing.

## Frontend - Run

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

App: <http://localhost:5173>

To make the frontend reachable from another system on the same network, run Vite with a host binding, for example:

```powershell
npm run dev -- --host 0.0.0.0
```

Then browse to the host machine IP, for example `http://192.168.29.80:5173/`.

For LAN browser access, the backend must also listen on the LAN interface:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Set `frontend/.env` to the same host IP, for example:

```text
VITE_API_BASE_URL=http://192.168.29.80:8000
```

If you are browsing from the same machine as the backend, `http://localhost:8000` is fine. For LAN access, make sure `backend/.env` allows the browser origin through `ALLOWED_ORIGINS` or `ALLOWED_ORIGIN_REGEX`.

## Try It

### Local System Agent

1. Start the local app at `http://127.0.0.1:8765/local-app`.
2. Open the app and click **Local System Agent**, or type a local workstation question.
3. Try read-only examples:
   - `how much disk space is free on C drive?`
   - `what is the current system time?`
   - `what is my computer name?`
   - `is DOTA2 installed?`
   - `what microphone is available?`
4. Review the highlighted permission prompt. The frontend shows the planned command before execution.
5. Approve the command to let the local app run it as the current user. The frontend sends the structured result and task context back to the backend, and the backend generates the final answer.

Local System Agent commands run only as the current user. The local app does not attempt administrator elevation; admin-only failures are reported as `needs_elevation`.

### System Slow Diagnostics

1. Open the app and click **System Slow Diagnostics** or type "My system is slow".
2. Built-in mock devices:
   - `LAPTOP-INTUNE-01` -> Intune adapter path.
   - `DESKTOP-SCCM-42` -> SCCM adapter path.
   - Any other name -> browser fallback with optional local app diagnostic results.
3. Review the diagnostic and ticket-draft cards.
4. Reply `yes` to create the mock ticket.
5. Visit **Tickets** to see created mock tickets.

### Windows Update Failure

1. Type "windows update failing".
2. The agent chooses one troubleshooting check at a time.
3. After enough checks, or if you ask to launch/check the local agent, it asks once for explicit workstation access.
4. Reply with a clear approval such as `yes`, `yes confirmed`, or `yes access the workstation`.
5. The workflow triggers the allowlisted `collect_windows_update_status` local app action first, then continues based on the result.

## Architecture Notes

- **Workflow registry** (`app/services/workflow_registry.py`) - every workflow implements `BaseWorkflow.handle(session, message)`. Adding a new workflow means adding a module and one registry entry.
- **Conversation router** (`app/agents/conversation_agent.py`) - routes top-level user messages into workflows and preserves sticky routing while a workflow is waiting for follow-up.
- **Diagnostic router** (`app/services/diagnostic_router.py`) - fixed priority: Intune -> SCCM -> Browser fallback. Browser fallback can call the local app over localhost.
- **Local System Agent** (`app/workflows/local_system_agent/workflow.py`) - backend-planned, confirmation-gated current-user PowerShell tasks. It carries task context through the frontend/local-app result path so the backend can answer directly instead of echoing raw output.
- **Local app server** (`local_app/`) - localhost JSON-RPC app exposing `diagnostics.search`, allowlisted remediation tools, Windows Update actions, and `actions.run_powershell_task`.
- **Cards** - backend returns generic `UICard{kind,data}` items; the frontend card renderer can show workflow-specific structured output.
- **Security** - the backend plans local actions, the frontend asks for user approval, and the local app executes only after approval. Generic PowerShell tasks run as the current user with timeouts, output capture, and no elevation attempt. Workflow-specific tools remain allowlisted and ticket creation still requires confirmation.

## Roadmap

| Iteration | Scope |
| --- | --- |
| 1 | Generic shell + System Slow + Windows Update + mocks |
| 2 | Real Intune via Microsoft Graph |
| 3 | Real SCCM/MECM |
| 4 | Hardened local app deployment |
| 5 | ServiceNow / Jira ticketing |
