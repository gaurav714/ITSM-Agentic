# AI Helpdesk Assistant Platform

Generic AI-powered IT helpdesk assistant with a modular workflow registry. Iteration 1 implements **System Slow Diagnostics** end-to-end with mock Intune/SCCM adapters and browser/local-app diagnostics. The **Windows Update Failure** workflow is also active and uses an LLM-driven LangGraph decision loop for troubleshooting checks, explicit local-access approval, and allowlisted local app tools.

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

LLM keys are optional for most platform behavior. Without `OPENAI_API_KEY`, the intent router falls back to a deterministic keyword classifier. The Windows Update agentic decision loop requires a configured LLM unless `WINDOWS_UPDATE_ALLOW_DETERMINISTIC_FALLBACK=true` is explicitly enabled for demo/testing.

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

## Try It

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
- **Local app server** (`local_app/`) - localhost JSON-RPC app exposing allowlisted diagnostic/remediation tools for browser fallback and Windows Update troubleshooting.
- **Cards** - backend returns generic `UICard{kind,data}` items; the frontend card renderer can show workflow-specific structured output.
- **Security** - the LLM never executes arbitrary commands. It can select only allowlisted workflow tools, and deterministic gates still enforce local-access approval, tool allowlists, and ticket confirmation.

## Roadmap

| Iteration | Scope |
| --- | --- |
| 1 | Generic shell + System Slow + Windows Update + mocks |
| 2 | Real Intune via Microsoft Graph |
| 3 | Real SCCM/MECM |
| 4 | Hardened local app deployment |
| 5 | ServiceNow / Jira ticketing |
