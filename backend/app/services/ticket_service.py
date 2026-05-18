"""Ticket service — generates draft text and creates mock tickets."""

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.adapters.ticketing.mock_ticket_adapter import mock_ticket_adapter
from app.models.schemas import TicketDraft
from app.services.llm import llm_structured
from app.workflows.system_slow.prompts import TICKET_DRAFT_PROMPT


class _LLMTicketDraft(BaseModel):
    title: str = Field(..., max_length=120)
    description: str
    priority: Literal["Low", "Medium", "High"]


def generate_ticket_draft(session: Dict[str, Any]) -> TicketDraft:
    device = session.get("device_name") or "Unknown device"
    diagnostic = session.get("diagnostic") or {}
    method = diagnostic.get("method", "unknown")

    # Try LLM first.
    llm_draft = _llm_draft(device, method, diagnostic)
    if llm_draft is not None:
        return TicketDraft(
            session_id=session.get("session_id", ""),
            title=llm_draft.title[:120],
            description=llm_draft.description,
            category="Endpoint Performance",
            priority=llm_draft.priority,
            device_name=device,
            diagnostic_id=session.get("diagnostic_id"),
        )

    # Deterministic fallback.
    cpu = diagnostic.get("cpu_pct")
    mem = diagnostic.get("memory_pct")
    disk = diagnostic.get("disk_free_gb")
    procs = diagnostic.get("top_processes") or []
    local_summary = diagnostic.get("local_app_summary")
    recommendation = diagnostic.get("diagnostic_recommendation")

    lines = [
        f"User reports system slowness on device: {device}.",
        f"Diagnostic method: {method}.",
    ]
    if cpu is not None:
        lines.append(f"CPU utilization: {cpu}%.")
    if mem is not None:
        lines.append(f"Memory utilization: {mem}%.")
    if disk is not None:
        lines.append(f"Free disk: {disk} GB.")
    if procs:
        lines.append(f"Top processes: {', '.join(procs)}.")
    if local_summary:
        lines.append(f"Local app server summary: {local_summary}.")
    if recommendation:
        lines.append(f"Recommended next step: {recommendation}.")
    if method == "browser_only":
        lines.append(
            "Limited enterprise diagnostics — device not enrolled in Intune/SCCM/enterprise endpoint agent. "
            "Recommend using the local app server output or collecting deeper endpoint logs."
        )

    priority = "High" if (cpu and cpu >= 85) or (mem and mem >= 85) else "Medium"

    return TicketDraft(
        session_id=session.get("session_id", ""),
        title=f"System slow — {device}",
        description="\n".join(lines),
        category="Endpoint Performance",
        priority=priority,
        device_name=device,
        diagnostic_id=session.get("diagnostic_id"),
    )


def _llm_draft(device: str, method: str, diagnostic: Dict[str, Any]):
    metric_keys = (
        "cpu_pct",
        "memory_pct",
        "disk_free_gb",
        "top_processes",
        "cpu_cores",
        "physical_cpu_cores",
        "logical_cpu_cores",
        "browser_hardware_concurrency",
        "device_memory_gb",
        "online",
        "page_load_ms",
        "local_app_available",
        "local_app_summary",
        "diagnostic_recommendation",
        "tool_candidates",
    )
    metric_lines = [
        f"- {k}: {diagnostic[k]}"
        for k in metric_keys
        if diagnostic.get(k) not in (None, [], "")
    ]
    metrics_block = "\n".join(metric_lines) or "(no metrics available)"
    return llm_structured(
        TICKET_DRAFT_PROMPT.format(device=device, method=method, metrics=metrics_block),
        _LLMTicketDraft,
    )


def create_ticket(draft: TicketDraft) -> Dict[str, Any]:
    return mock_ticket_adapter.create(draft.model_dump())
