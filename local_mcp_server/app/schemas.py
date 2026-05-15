"""Request/response schemas for the local diagnostic MCP server."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiagnosticContext(BaseModel):
    session_id: Optional[str] = None
    device_name: Optional[str] = None
    diagnostic_id: Optional[str] = None
    browser_metrics: Dict[str, Any] = Field(default_factory=dict)


class DiagnosticSearchRequest(BaseModel):
    query: str
    context: DiagnosticContext = Field(default_factory=DiagnosticContext)


class ToolResult(BaseModel):
    name: str
    status: str
    description: str
    result: Dict[str, Any] = Field(default_factory=dict)


class ActionOption(BaseModel):
    id: str
    label: str
    description: str
    available: bool = False


class DiagnosticSearchResponse(BaseModel):
    summary: str
    recommendation: str
    tools: List[ToolResult] = Field(default_factory=list)
    actions: List[ActionOption] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class ActionExecutionRequest(BaseModel):
    action: str
    context: DiagnosticContext = Field(default_factory=DiagnosticContext)


class ActionExecutionResponse(BaseModel):
    action: str
    status: str
    message: str
    stopped_processes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
