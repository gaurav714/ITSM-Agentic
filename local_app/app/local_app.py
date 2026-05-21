"""Minimal JSON-RPC surface for local diagnostic tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.agent import diagnose
from app.schemas import (
    ActionExecutionRequest,
    ActionExecutionResponse,
    DiagnosticContext,
    DiagnosticSearchRequest,
)
from app.tools import (
    collect_windows_update_status,
    open_windows_update_settings,
    stop_edge_processes,
)


class LocalAppRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


def handle_local_app_request(request: LocalAppRequest) -> Dict[str, Any]:
    if request.jsonrpc != "2.0":
        return _error(request.id, -32600, "Invalid JSON-RPC version.")

    if request.method == "initialize":
        return _result(
            request.id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {
                    "name": "local-diagnostic-app",
                    "version": "0.1.0",
                },
                "capabilities": {"tools": {}},
            },
        )

    if request.method == "tools/list":
        return _result(request.id, {"tools": _tool_definitions()})

    if request.method == "tools/call":
        return _call_tool(request)

    return _error(request.id, -32601, f"Unsupported local app method: {request.method}")


def _call_tool(request: LocalAppRequest) -> Dict[str, Any]:
    name = request.params.get("name")
    arguments = request.params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(request.id, -32602, "Tool arguments must be an object.")

    if name == "diagnostics.search":
        diagnostic_request = DiagnosticSearchRequest(
            query=str(arguments.get("query") or "system is slow"),
            context=_context_from_arguments(arguments),
        )
        response = diagnose(diagnostic_request).model_dump()
        return _tool_result(request.id, response)

    if name == "actions.stop_edge":
        action_request = ActionExecutionRequest(
            action=str(arguments.get("action") or "stop_edge"),
            context=_context_from_arguments(arguments),
        )
        if action_request.action != "stop_edge":
            response = ActionExecutionResponse(
                action=action_request.action,
                status="rejected",
                message="Only the stop_edge action is allowlisted.",
            ).model_dump()
            return _tool_result(request.id, response)

        result = stop_edge_processes()
        response = ActionExecutionResponse(
            action="stop_edge",
            status=result["status"],
            message=result["message"],
            stopped_processes=result["stopped_processes"],
            errors=result["errors"],
        ).model_dump()
        return _tool_result(request.id, response)

    if name == "actions.open_windows_update_settings":
        action_request = ActionExecutionRequest(
            action=str(arguments.get("action") or "open_windows_update_settings"),
            context=_context_from_arguments(arguments),
        )
        if action_request.action != "open_windows_update_settings":
            response = ActionExecutionResponse(
                action=action_request.action,
                status="rejected",
                message="Only the open_windows_update_settings action is allowlisted here.",
            ).model_dump()
            return _tool_result(request.id, response)

        result = open_windows_update_settings()
        response = ActionExecutionResponse(
            action="open_windows_update_settings",
            status=result["status"],
            message=result["message"],
            errors=result["errors"],
            opened_uri=result["opened_uri"],
        ).model_dump()
        return _tool_result(request.id, response)

    if name == "actions.collect_windows_update_status":
        action_request = ActionExecutionRequest(
            action=str(arguments.get("action") or "collect_windows_update_status"),
            context=_context_from_arguments(arguments),
        )
        if action_request.action != "collect_windows_update_status":
            response = ActionExecutionResponse(
                action=action_request.action,
                status="rejected",
                message="Only the collect_windows_update_status action is allowlisted here.",
            ).model_dump()
            return _tool_result(request.id, response)

        result = collect_windows_update_status()
        response = ActionExecutionResponse(
            action="collect_windows_update_status",
            status=result["status"],
            message=result["message"],
            errors=result["errors"],
            service_statuses=result["service_statuses"],
            pending_reboot=result["pending_reboot"],
        ).model_dump()
        return _tool_result(request.id, response)

    return _error(request.id, -32602, f"Unknown local app tool: {name}")


def _context_from_arguments(arguments: Dict[str, Any]) -> DiagnosticContext:
    context = arguments.get("context") or {}
    if not isinstance(context, dict):
        context = {}
    return DiagnosticContext(**context)


def _tool_result(request_id: Optional[str | int], structured_content: Dict[str, Any]):
    return _result(
        request_id,
        {
            "content": [
                {
                    "type": "text",
                    "text": structured_content.get("summary")
                    or structured_content.get("message")
                    or "Tool completed.",
                }
            ],
            "structuredContent": structured_content,
            "isError": False,
        },
    )


def _tool_definitions() -> list[Dict[str, Any]]:
    return [
        {
            "name": "diagnostics.search",
            "description": "Run allowlisted local diagnostics for a user workstation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "context": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "device_name": {"type": "string"},
                            "diagnostic_id": {"type": "string"},
                            "browser_metrics": {"type": "object"},
                        },
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "actions.stop_edge",
            "description": "Stop Microsoft Edge processes after explicit user approval.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "const": "stop_edge"},
                    "context": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "device_name": {"type": "string"},
                            "diagnostic_id": {"type": "string"},
                        },
                    },
                },
            },
        },
        {
            "name": "actions.open_windows_update_settings",
            "description": "Open Windows Update settings after explicit user approval.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "const": "open_windows_update_settings",
                    },
                    "context": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "device_name": {"type": "string"},
                        },
                    },
                },
            },
        },
        {
            "name": "actions.collect_windows_update_status",
            "description": "Read Windows Update related service status and pending reboot state after explicit user approval.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "const": "collect_windows_update_status",
                    },
                    "context": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "device_name": {"type": "string"},
                        },
                    },
                },
            },
        },
    ]


def _result(request_id: Optional[str | int], result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(
    request_id: Optional[str | int], code: int, message: str
) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
