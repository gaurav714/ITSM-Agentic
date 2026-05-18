"""FastAPI application entry point."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.adapters.browser.adapter import browser_adapter
from app.adapters.identity.mock_identity_adapter import mock_identity_adapter
from app.adapters.ticketing.mock_ticket_adapter import mock_ticket_adapter
from app.agents.conversation_agent import handle_user_message
from app.config import get_settings
from app.memory.session_store import session_store
from app.models.schemas import (
    AgentMessageRequest,
    AgentMessageResponse,
    BrowserDiagnosticsPayload,
    DiagnosticResultResponse,
    DiagnosticStartRequest,
    LocalActionRequest,
    LocalActionResultPayload,
    TicketCreateRequest,
    TicketCreateResponse,
    TicketDraft,
    TicketDraftRequest,
)
from app.services.diagnostic_router import run_diagnostics
from app.services.local_diagnostic_tools import execute_local_action
from app.services.ticket_service import create_ticket, generate_ticket_draft
from app.services.workflow_registry import list_workflows

settings = get_settings()
app = FastAPI(title="AI Helpdesk Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/workflows")
def workflows() -> list:
    return list_workflows()


# ---- Conversational endpoint -------------------------------------------------
class StartWorkflowRequest(BaseModel):
    session_id: Optional[str] = None
    workflow_id: str


@app.post("/agent/message", response_model=AgentMessageResponse)
def agent_message(req: AgentMessageRequest) -> AgentMessageResponse:
    if not req.session_id:
        raise HTTPException(400, "session_id is required")
    return handle_user_message(req.session_id, req.message)


@app.post("/agent/start_workflow", response_model=AgentMessageResponse)
def agent_start_workflow(req: StartWorkflowRequest) -> AgentMessageResponse:
    session_id = req.session_id or uuid.uuid4().hex
    # Reset session state so the chosen workflow starts cleanly.
    session_store.update(session_id, workflow=None, state="idle")
    return handle_user_message(session_id, "", forced_workflow=req.workflow_id)


# ---- Diagnostics -------------------------------------------------------------
@app.post("/diagnostics/start", response_model=DiagnosticResultResponse)
def diagnostics_start(req: DiagnosticStartRequest) -> DiagnosticResultResponse:
    diagnostic = run_diagnostics(req.device_name, req.session_id)
    diagnostic_id = f"DIAG-{uuid.uuid4().hex[:8].upper()}"
    session_store.update(
        req.session_id,
        device_name=req.device_name,
        diagnostic_id=diagnostic_id,
        diagnostic=diagnostic,
    )
    return DiagnosticResultResponse(
        diagnostic_id=diagnostic_id,
        status="complete",
        method=diagnostic.get("method"),
        metrics=diagnostic,
    )


@app.get("/diagnostics/{diagnostic_id}", response_model=DiagnosticResultResponse)
def diagnostics_get(diagnostic_id: str) -> DiagnosticResultResponse:
    # Iterate sessions to find a matching diagnostic id (mock implementation).
    for sess in session_store._sessions.values():  # noqa: SLF001 — mock storage
        if sess.get("diagnostic_id") == diagnostic_id:
            return DiagnosticResultResponse(
                diagnostic_id=diagnostic_id,
                status="complete",
                method=(sess.get("diagnostic") or {}).get("method"),
                metrics=sess.get("diagnostic") or {},
                summary=sess.get("summary"),
            )
    raise HTTPException(404, "Diagnostic not found")


@app.post("/diagnostics/browser")
def diagnostics_browser(payload: BrowserDiagnosticsPayload) -> dict:
    browser_adapter.submit(payload.session_id, payload.model_dump())
    return {"status": "received"}


@app.post("/diagnostics/action", response_model=LocalActionResultPayload)
def diagnostics_action(req: LocalActionRequest) -> LocalActionResultPayload:
    result = execute_local_action(
        req.action,
        {
            "session_id": req.session_id,
            "device_name": req.device_name,
            "diagnostic_id": req.diagnostic_id,
        },
    )
    payload = LocalActionResultPayload(
        session_id=req.session_id,
        **result.model_dump(),
        raw=result.model_dump(),
    )
    session_store.update(req.session_id, local_action_result=payload.model_dump())
    return payload


# ---- Tickets -----------------------------------------------------------------
@app.post("/tickets/draft", response_model=TicketDraft)
def tickets_draft(req: TicketDraftRequest) -> TicketDraft:
    sess = session_store.get(req.session_id)
    sess["session_id"] = req.session_id
    draft = generate_ticket_draft(sess)
    sess["ticket_draft"] = draft.model_dump()
    return draft


@app.post("/tickets/create", response_model=TicketCreateResponse)
def tickets_create(req: TicketCreateRequest) -> TicketCreateResponse:
    ticket = create_ticket(req.draft)
    session_store.update(
        req.session_id, ticket_id=ticket["ticket_id"], state="complete"
    )
    return TicketCreateResponse(
        ticket_id=ticket["ticket_id"],
        status=ticket["status"],
        message=f"Ticket {ticket['ticket_id']} created.",
    )


@app.get("/tickets")
def tickets_list() -> list:
    return mock_ticket_adapter.list()


@app.get("/identity/users")
def identity_users_list() -> list:
    return mock_identity_adapter.list_users()
