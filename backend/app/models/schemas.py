"""Pydantic request/response models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    session_id: str = Field(..., description="Stable client-generated session id")
    message: str


class UICard(BaseModel):
    """Generic UI card payload — frontend renders by `kind`."""

    kind: str  # workflow | diagnostic_status | diagnostic_result | ticket_draft | confirmation
    data: Dict[str, Any] = Field(default_factory=dict)


class AgentMessageResponse(BaseModel):
    type: str = "assistant_message"
    message: str
    workflow: Optional[str] = None
    state: Optional[str] = None
    cards: List[UICard] = Field(default_factory=list)
    requires_input: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DiagnosticStartRequest(BaseModel):
    session_id: str
    device_name: str


class DiagnosticResultResponse(BaseModel):
    diagnostic_id: str
    status: str  # pending | running | complete | failed
    method: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None


class BrowserDiagnosticsPayload(BaseModel):
    session_id: str
    device_name: Optional[str] = None
    diagnostic_id: Optional[str] = None
    user_agent: Optional[str] = None
    platform: Optional[str] = None
    cpu_cores: Optional[int] = None
    device_memory_gb: Optional[float] = None
    online: Optional[bool] = None
    connection_type: Optional[str] = None
    page_load_ms: Optional[float] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class LocalActionResultPayload(BaseModel):
    session_id: str
    action: str
    status: str
    message: str
    stopped_processes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    opened_uri: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class LocalActionRequest(BaseModel):
    session_id: str
    action: str
    device_name: Optional[str] = None
    diagnostic_id: Optional[str] = None


class TicketDraftRequest(BaseModel):
    session_id: str


class TicketDraft(BaseModel):
    session_id: str
    title: str
    description: str
    category: str = "Endpoint Performance"
    priority: str = "Medium"
    device_name: Optional[str] = None
    diagnostic_id: Optional[str] = None


class TicketCreateRequest(BaseModel):
    session_id: str
    draft: TicketDraft


class TicketCreateResponse(BaseModel):
    ticket_id: str
    status: str = "Open"
    message: str
