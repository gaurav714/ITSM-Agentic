"""Tool-using system slow diagnostics agent.

The workflow gathers the device name and handles the browser diagnostics
handshake. Once diagnostics are ready to run, this module lets a LangGraph
ReAct agent decide and execute the approved diagnostic tools. If no LLM is
configured, it falls back to the same deterministic sequence.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.services.diagnostic_router import (
    run_diagnostics,
    select_diagnostic_method as choose_diagnostic_method,
)
from app.services.llm import llm_client, llm_text
from app.services.ticket_service import generate_ticket_draft
from app.workflows.system_slow.prompts import SYSTEM_SUMMARY_PROMPT


def run_system_slow_agent(
    device_name: str, session_id: str, diagnostic_id: str
) -> Dict[str, Any]:
    trace: list[dict] = []
    tools = _build_tools(trace)
    llm = llm_client()

    if llm is None:
        return _run_deterministic_tool_fallback(
            device_name, session_id, diagnostic_id, trace
        )

    agent = create_react_agent(
        llm,
        tools,
        messages_modifier=(
            "You are an enterprise endpoint diagnostics agent. You may only use "
            "the provided tools. Select the best diagnostic method, run "
            "diagnostics for the device, and prepare a support ticket draft. If "
            "browser-submitted local agent data is present in diagnostics, use it "
            "as telemetry only. Never invent device metrics or ticket details. "
            "Return a concise summary of the performed tool calls."
        ),
    )
    objective = {
        "device_name": device_name,
        "session_id": session_id,
        "diagnostic_id": diagnostic_id,
        "required_steps": [
            "select_diagnostic_method",
            "run_system_diagnostics",
            "prepare_ticket_draft",
        ],
    }

    try:
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "Execute this approved system slow diagnostic request "
                            "using tools:\n"
                            + json.dumps(objective, indent=2)
                        )
                    )
                ]
            }
        )
        final_message = result["messages"][-1].content if result.get("messages") else ""
        return _build_agent_result(
            device_name,
            session_id,
            diagnostic_id,
            trace,
            True,
            final_message,
        )
    except Exception as exc:
        fallback = _run_deterministic_tool_fallback(
            device_name, session_id, diagnostic_id, trace
        )
        fallback["agent_error"] = str(exc)
        return fallback


def _build_tools(trace: list[dict]):
    @tool
    def select_diagnostic_method(device_name: str) -> Dict[str, Any]:
        """Select the best available diagnostic method for an endpoint."""
        method = choose_diagnostic_method(device_name)
        event = {
            "tool": "select_diagnostic_method",
            "status": "complete",
            "device_name": device_name,
            "method": method,
        }
        trace.append(event)
        return event

    @tool
    def run_system_diagnostics(device_name: str, session_id: str) -> Dict[str, Any]:
        """Collect normalized endpoint performance diagnostics."""
        diagnostic = run_diagnostics(device_name, session_id)
        event = {
            "tool": "run_system_diagnostics",
            "status": "complete",
            "device_name": device_name,
            "method": diagnostic.get("method"),
            "result": diagnostic,
        }
        trace.append(event)
        return event

    @tool
    def prepare_ticket_draft(
        device_name: str, session_id: str, diagnostic_id: str
    ) -> Dict[str, Any]:
        """Prepare a support ticket draft from the latest diagnostic result."""
        diagnostic = _latest_diagnostic(trace)
        if diagnostic is None:
            diagnostic = run_diagnostics(device_name, session_id)
            trace.append(
                {
                    "tool": "run_system_diagnostics",
                    "status": "complete",
                    "device_name": device_name,
                    "method": diagnostic.get("method"),
                    "result": diagnostic,
                }
            )

        draft = generate_ticket_draft(
            {
                "session_id": session_id,
                "device_name": device_name,
                "diagnostic_id": diagnostic_id,
                "diagnostic": diagnostic,
            }
        )
        event = {
            "tool": "prepare_ticket_draft",
            "status": "complete",
            "device_name": device_name,
            "result": draft.model_dump(),
        }
        trace.append(event)
        return event

    return [
        select_diagnostic_method,
        run_system_diagnostics,
        prepare_ticket_draft,
    ]


def _run_deterministic_tool_fallback(
    device_name: str, session_id: str, diagnostic_id: str, trace: list[dict]
) -> Dict[str, Any]:
    method = choose_diagnostic_method(device_name)
    trace.append(
        {
            "tool": "select_diagnostic_method",
            "status": "complete",
            "device_name": device_name,
            "method": method,
        }
    )

    diagnostic = run_diagnostics(device_name, session_id)
    trace.append(
        {
            "tool": "run_system_diagnostics",
            "status": "complete",
            "device_name": device_name,
            "method": diagnostic.get("method"),
            "result": diagnostic,
        }
    )

    draft = generate_ticket_draft(
        {
            "session_id": session_id,
            "device_name": device_name,
            "diagnostic_id": diagnostic_id,
            "diagnostic": diagnostic,
        }
    )
    trace.append(
        {
            "tool": "prepare_ticket_draft",
            "status": "complete",
            "device_name": device_name,
            "result": draft.model_dump(),
        }
    )

    return _build_agent_result(
        device_name,
        session_id,
        diagnostic_id,
        trace,
        False,
        "No LLM configured. Executed diagnostics and ticket draft deterministically.",
    )


def _build_agent_result(
    device_name: str,
    session_id: str,
    diagnostic_id: str,
    trace: list[dict],
    used_llm_agent: bool,
    summary: str,
) -> Dict[str, Any]:
    diagnostic = _latest_diagnostic(trace)
    if diagnostic is None:
        diagnostic = run_diagnostics(device_name, session_id)
        trace.append(
            {
                "tool": "run_system_diagnostics",
                "status": "complete",
                "device_name": device_name,
                "method": diagnostic.get("method"),
                "result": diagnostic,
            }
        )

    effective_device_name = _device_name_from_diagnostic(diagnostic, device_name)

    ticket_draft = _latest_ticket_draft(trace)
    if ticket_draft is None or effective_device_name != device_name:
        draft = generate_ticket_draft(
            {
                "session_id": session_id,
                "device_name": effective_device_name,
                "diagnostic_id": diagnostic_id,
                "diagnostic": diagnostic,
            }
        )
        ticket_draft = draft.model_dump()
        trace.append(
            {
                "tool": "prepare_ticket_draft",
                "status": "complete",
                "device_name": device_name,
                "result": ticket_draft,
            }
        )

    diagnostic_summary = _summarize(diagnostic, effective_device_name)
    return {
        "agentic": used_llm_agent,
        "agent_summary": summary,
        "device_name": effective_device_name,
        "diagnostic": diagnostic,
        "summary": diagnostic_summary,
        "ticket_draft": ticket_draft,
        "tool_trace": trace,
    }


def _latest_diagnostic(trace: list[dict]) -> Optional[Dict[str, Any]]:
    for event in reversed(trace):
        if event.get("tool") == "run_system_diagnostics" and event.get("result"):
            return event["result"]
    return None


def _latest_ticket_draft(trace: list[dict]) -> Optional[Dict[str, Any]]:
    for event in reversed(trace):
        if event.get("tool") == "prepare_ticket_draft" and event.get("result"):
            return event["result"]
    return None


def _device_name_from_diagnostic(
    diagnostic: Dict[str, Any], fallback: str
) -> str:
    for key in ("hostname", "device_name"):
        value = diagnostic.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    local_agent_response = diagnostic.get("local_agent_response")
    if isinstance(local_agent_response, dict):
        local_metrics = local_agent_response.get("metrics")
        if isinstance(local_metrics, dict):
            hostname = local_metrics.get("hostname")
            if isinstance(hostname, str) and hostname.strip():
                return hostname.strip()

    return fallback


def _summarize(diagnostic: Dict[str, Any], device_name: str) -> str:
    method = diagnostic.get("method")
    metric_keys = (
        "cpu_pct",
        "memory_pct",
        "disk_free_gb",
        "top_processes",
        "cpu_cores",
        "device_memory_gb",
        "online",
        "page_load_ms",
        "local_agent_available",
        "local_agent_summary",
        "diagnostic_recommendation",
        "tool_candidates",
        "remediation_actions",
        "edge_running",
    )
    metric_lines = [
        f"- {key}: {diagnostic[key]}"
        for key in metric_keys
        if diagnostic.get(key) not in (None, [], "")
    ]
    metrics_block = "\n".join(metric_lines) or "(no metrics available)"

    llm_summary = llm_text(
        SYSTEM_SUMMARY_PROMPT.format(
            device=device_name,
            method=method,
            metrics=metrics_block,
        )
    )
    if llm_summary:
        return llm_summary

    cpu = diagnostic.get("cpu_pct")
    mem = diagnostic.get("memory_pct")
    disk = diagnostic.get("disk_free_gb")
    procs = diagnostic.get("top_processes") or []

    bits = [f"Diagnostics for {device_name} via {method}:"]
    if cpu is not None:
        bits.append(f"CPU at {cpu}%.")
    if mem is not None:
        bits.append(f"Memory at {mem}%.")
    if disk is not None:
        bits.append(f"{disk} GB disk free.")
    if procs:
        bits.append(f"Top processes: {', '.join(procs[:3])}.")
    if diagnostic.get("local_agent_summary"):
        bits.append(f"Local diagnostic assistant: {diagnostic['local_agent_summary']}")
    if diagnostic.get("diagnostic_recommendation"):
        bits.append(f"Recommendation: {diagnostic['diagnostic_recommendation']}")
    if method == "browser_only":
        if diagnostic.get("local_agent_available"):
            bits.append("Browser metrics were enriched by the local diagnostic assistant.")
        else:
            bits.append(
                "Only browser-level metrics were available; install or start the local diagnostic assistant for deeper diagnostics."
            )
    elif cpu and cpu >= 85:
        bits.append("CPU pressure is the likely cause; consider closing high-CPU processes.")
    elif mem and mem >= 85:
        bits.append("Memory pressure is the likely cause; a reboot or closing apps may help.")
    elif disk is not None and disk < 10:
        bits.append("Low free disk space is likely contributing; free up space.")
    return " ".join(bits)
