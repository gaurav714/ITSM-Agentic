# AI Helpdesk Assistant Platform

Generic AI-powered IT helpdesk assistant with a modular workflow registry. Iteration 1 implements the **System Slow Diagnostics** workflow end-to-end with mock Intune / SCCM adapters and a browser-diagnostics fallback that the backend enriches with allowlisted local diagnostic tools.

## Project Layout

```text
backend/    FastAPI + LangGraph + LangChain
frontend/   React + Vite + Tailwind + React Query + Zustand + Axios
docs/       Project notes and workflow documentation
```

## Backend - Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Health check: <http://localhost:8000/health>
OpenAPI docs: <http://localhost:8000/docs>

LLM keys are optional. Without `OPENAI_API_KEY` the intent router falls back to a deterministic keyword classifier.

## Frontend - Run

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

App: <http://localhost:5173>

## Try It

1. Open the app and click **System Slow Diagnostics** or type "My system is slow".
2. Built-in mock device paths:
   - `LAPTOP-INTUNE-01` -> Intune adapter path.
   - `DESKTOP-SCCM-42` -> SCCM adapter path.
   - Any other name -> browser fallback; frontend submits browser metrics and backend-local tools enrich the result.
3. Review the diagnostic and ticket-draft cards; reply `yes` to create the mock ticket.
4. Visit **Tickets** to see created mock tickets.

## Architecture Notes

- **Workflow registry** (`app/services/workflow_registry.py`) - every workflow implements `BaseWorkflow.handle(session, message)`.
- **Diagnostic router** (`app/services/diagnostic_router.py`) - fixed priority: Intune -> SCCM -> Browser fallback with backend-local diagnostic enrichment.
- **Backend-local tools** (`app/services/local_diagnostic_tools.py`) - allowlisted diagnostic/remediation tools executed by the backend running on the workstation.
- **Cards** - backend returns generic `UICard{kind,data}` items; the frontend has a card-renderer registry.
- **Security** - the LLM never executes commands. Tools are allowlisted, and side-effectful actions require explicit user confirmation.

See [Technology Rationale](docs/technology-rationale.md) for the technology stack and the reasoning behind each choice. See [Workflow Flowcharts](docs/workflow-flowcharts.md) for diagrams of the main workflow paths.

## Roadmap

| Iteration | Scope |
| --------- | ----- |
| 1 | Generic shell + System Slow + mocks |
| 2 | Real Intune via Microsoft Graph |
| 3 | Real SCCM/MECM |
| 4 | Hardened endpoint diagnostics |
| 5 | ServiceNow / Jira ticketing |
