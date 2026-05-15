"""FastAPI entry point for the local diagnostic assistant."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import diagnose
from app.schemas import (
    ActionExecutionRequest,
    ActionExecutionResponse,
    DiagnosticSearchRequest,
    DiagnosticSearchResponse,
)
from app.tools import stop_edge_processes

app = FastAPI(title="Local Diagnostic Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.29.13:5173",
    ],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/diagnostics/search", response_model=DiagnosticSearchResponse)
def diagnostics_search(req: DiagnosticSearchRequest) -> DiagnosticSearchResponse:
    return diagnose(req)


@app.post("/actions/stop-edge", response_model=ActionExecutionResponse)
def stop_edge(req: ActionExecutionRequest) -> ActionExecutionResponse:
    if req.action != "stop_edge":
        return ActionExecutionResponse(
            action=req.action,
            status="rejected",
            message="Only the stop_edge action is allowlisted.",
        )

    result = stop_edge_processes()
    return ActionExecutionResponse(
        action="stop_edge",
        status=result["status"],
        message=result["message"],
        stopped_processes=result["stopped_processes"],
        errors=result["errors"],
    )
