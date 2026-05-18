"""Selects the best available diagnostic method per the priority order."""

from typing import Any, Dict, Optional

from app.adapters.browser.adapter import browser_adapter
from app.adapters.intune.adapter import intune_adapter
from app.adapters.sccm.adapter import sccm_adapter
from app.services.local_diagnostic_tools import diagnose_local_system


def select_diagnostic_method(device_name: str) -> str:
    """Priority: Intune -> SCCM -> Browser fallback with backend-local tools."""
    if intune_adapter.device_exists(device_name):
        return "intune"
    if sccm_adapter.device_exists(device_name):
        return "sccm"
    return "browser_only"


def run_diagnostics(device_name: str, session_id: str) -> Dict[str, Any]:
    """Run diagnostics via the selected adapter and return a normalized result."""
    method = select_diagnostic_method(device_name)
    raw: Optional[Dict[str, Any]] = None

    if method == "intune":
        raw = intune_adapter.collect(device_name)
    elif method == "sccm":
        raw = sccm_adapter.collect(device_name)
    else:
        raw = browser_adapter.get(session_id)

    return normalize_results(method, raw or {})


def normalize_results(method: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map adapter-specific fields onto a common metric schema."""
    if method == "browser_only":
        raw = _with_backend_local_diagnostics(raw)

    metrics: Dict[str, Any] = {
        "method": method,
        "cpu_pct": raw.get("cpu_pct"),
        "memory_pct": raw.get("memory_pct"),
        "disk_free_gb": raw.get("disk_free_gb"),
        "top_processes": raw.get("top_processes", []),
        "raw": raw,
    }
    if method == "browser_only":
        metrics["browser_reported_cpu_cores"] = raw.get("cpu_cores")
        metrics["cpu_cores"] = raw.get("cpu_cores")
        metrics["device_memory_gb"] = raw.get("device_memory_gb")
        metrics["online"] = raw.get("online")
        metrics["page_load_ms"] = raw.get("page_load_ms")
        metrics["backend_local_available"] = raw.get("backend_local_available", False)
        metrics["backend_local_error"] = raw.get("backend_local_error")
        metrics["backend_local_response"] = raw.get("backend_local_response")
        if isinstance(raw.get("backend_local_response"), dict):
            backend_local_response = raw["backend_local_response"]
            local_metrics = backend_local_response.get("metrics")
            if isinstance(local_metrics, dict):
                for key in (
                    "cpu_pct",
                    "memory_pct",
                    "disk_free_gb",
                    "disk_total_gb",
                    "top_processes",
                    "hostname",
                    "os",
                    "machine",
                    "physical_cpu_cores",
                    "logical_cpu_processors",
                    "browser_reported_cpu_cores",
                ):
                    if metrics.get(key) in (None, []):
                        metrics[key] = local_metrics.get(key)
                metrics["cpu_cores"] = (
                    local_metrics.get("physical_cpu_cores")
                    or local_metrics.get("logical_cpu_processors")
                    or metrics.get("cpu_cores")
                )
                metrics["browser_reported_cpu_cores"] = raw.get(
                    "cpu_cores"
                ) or local_metrics.get("browser_reported_cpu_cores")
            metrics["tool_candidates"] = backend_local_response.get("tools", [])
            metrics["remediation_actions"] = backend_local_response.get("actions", [])
            metrics["edge_running"] = bool(metrics.get("edge_running")) or any(
                action.get("id") == "stop_edge" and action.get("available")
                for action in metrics["remediation_actions"]
                if isinstance(action, dict)
            )
            metrics["diagnostic_recommendation"] = backend_local_response.get(
                "recommendation"
            )
            metrics["backend_local_summary"] = backend_local_response.get("summary")
    return metrics


def _with_backend_local_diagnostics(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Add backend-local diagnostic output to browser-only telemetry."""
    if isinstance(raw.get("backend_local_response"), dict):
        return raw

    enriched = dict(raw)
    try:
        local_response = diagnose_local_system(
            "system is slow",
            {
                "session_id": raw.get("session_id"),
                "device_name": raw.get("device_name"),
                "diagnostic_id": raw.get("diagnostic_id"),
                "browser_metrics": raw,
            },
        ).model_dump()
        enriched["backend_local_available"] = True
        enriched["backend_local_response"] = local_response
        enriched["backend_local_error"] = None
    except Exception as exc:
        enriched["backend_local_available"] = False
        enriched["backend_local_response"] = None
        enriched["backend_local_error"] = f"backend_local_tools_error: {exc}"
    return enriched
