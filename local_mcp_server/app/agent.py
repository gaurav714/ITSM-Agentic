"""Small local diagnostic planner for system slowness requests."""

from __future__ import annotations

from app.schemas import ActionOption, DiagnosticSearchRequest, DiagnosticSearchResponse
from app.tools import is_edge_running, merge_metrics, run_tool, search_tools


def diagnose(request: DiagnosticSearchRequest) -> DiagnosticSearchResponse:
    tool_names = search_tools(request.query)
    tool_results = [run_tool(name, request.context) for name in tool_names]
    metrics = merge_metrics(tool_results)

    summary, recommendation, confidence = _summarize(metrics)
    return DiagnosticSearchResponse(
        summary=summary,
        recommendation=recommendation,
        tools=tool_results,
        actions=_actions_for_metrics(metrics),
        metrics=metrics,
        confidence=confidence,
    )


def _actions_for_metrics(metrics: dict) -> list[ActionOption]:
    edge_running = bool(metrics.get("edge_running")) or is_edge_running()
    return [
        ActionOption(
            id="stop_edge",
            label="Close Microsoft Edge",
            description="Stop Microsoft Edge browser processes running on this system.",
            available=edge_running,
        )
    ]


def _summarize(metrics: dict) -> tuple[str, str, float]:
    cpu = metrics.get("cpu_pct")
    memory = metrics.get("memory_pct")
    disk = metrics.get("disk_free_gb")

    if memory is not None and memory >= 85:
        return (
            f"High memory pressure detected at {memory}%.",
            "Close high-memory applications or restart the workstation; escalate if memory remains above 85%.",
            0.85,
        )
    if cpu is not None and cpu >= 85:
        return (
            f"High CPU pressure detected at {cpu}%.",
            "Close high-CPU applications and recheck; escalate if CPU remains above 85%.",
            0.85,
        )
    if disk is not None and disk < 10:
        return (
            f"Low disk space detected with {disk} GB free.",
            "Free disk space before collecting deeper logs.",
            0.8,
        )

    if any(key in metrics for key in ("cpu_pct", "memory_pct", "disk_free_gb")):
        return (
            "No severe local bottleneck was detected from the available metrics.",
            "Continue with backend diagnostics or collect endpoint logs if the slowness persists.",
            0.65,
        )

    return (
        "Only limited local telemetry was available.",
        "Install optional local metrics support or collect browser-only diagnostics.",
        0.4,
    )
