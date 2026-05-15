# AI Helpdesk Assistant Platform

Generic AI-powered IT helpdesk assistant with a modular workflow registry. Iteration 1 implements the **System Slow Diagnostics** workflow end-to-end with mock Intune / SCCM / local-agent adapters and a real browser-diagnostics fallback. Other workflows (Password Reset, VPN Access, …) are registered as "Coming soon" placeholders so the architecture is ready for them.

## Project layout

```
backend/    FastAPI + LangGraph + LangChain
frontend/   React + Vite + Tailwind + React Query + Zustand + Axios
```

## Backend — run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # optional — only needed for OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

Health check: <http://localhost:8000/health>
OpenAPI docs: <http://localhost:8000/docs>

LLM keys are optional. Without `OPENAI_API_KEY` the intent router falls back to a deterministic keyword classifier — sufficient for the iteration 1 acceptance criteria.

## Frontend — run

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

App: <http://localhost:5173>

## Try it

1. Open the app and click **System Slow Diagnostics** (or type "My system is slow").
2. When prompted, enter a device name. Built-in mocks:
   - `LAPTOP-INTUNE-01` → Intune adapter path (high CPU/memory)
   - `DESKTOP-SCCM-42` → SCCM adapter path
   - `WS-AGENT-7` → local-agent adapter path
   - any other name → browser fallback (frontend submits real browser metrics)
3. Review the diagnostic and ticket-draft cards; reply `yes` to create the mock ticket.
4. Visit **Tickets** to see the created mock tickets.

## Architecture notes

- **Workflow registry** (`app/services/workflow_registry.py`) — every workflow implements `BaseWorkflow.handle(session, message)`. Adding a new workflow = new module + one registry entry.
- **Diagnostic router** (`app/services/diagnostic_router.py`) — fixed priority: Intune → SCCM → Custom Agent → Browser fallback. Adapters share a uniform `device_exists` / `collect` shape.
- **Cards** — backend returns generic `UICard{kind,data}` items; the frontend has a card-renderer registry, so new workflows can ship new card kinds without changing `ChatWindow`.
- **Security** — the LLM never executes commands. It only classifies intent and (optionally) summarizes results. Tickets are only created after explicit user confirmation. Adapters are an allowlist.

## Roadmap

| Iteration | Scope                               |
| --------- | ----------------------------------- |
| 1 (this)  | Generic shell + System Slow + mocks |
| 2         | Real Intune via Microsoft Graph     |
| 3         | Real SCCM/MECM                      |
| 4         | Real local endpoint agent           |
| 5         | ServiceNow / Jira ticketing         |
