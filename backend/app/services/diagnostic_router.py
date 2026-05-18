"""Selects the best available diagnostic method per the priority order."""

from typing import Any, Dict, Optional

from app.adapters.browser.adapter import browser_adapter
from app.adapters.intune.adapter import intune_adapter
from app.adapters.sccm.adapter import sccm_adapter


def select_diagnostic_method(device_name: str) -> str:
    """Priority: Intune -> SCCM -> Browser fallback with optional local app."""
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
    metrics: Dict[str, Any] = {
        "method": method,
        "cpu_pct": raw.get("cpu_pct"),
        "memory_pct": raw.get("memory_pct"),
        "disk_free_gb": raw.get("disk_free_gb"),
        "top_processes": raw.get("top_processes", []),
        "raw": raw,
    }
    if method == "browser_only":
        metrics["browser_hardware_concurrency"] = raw.get(
            "browser_hardware_concurrency"
        ) or raw.get("cpu_cores")
        metrics["physical_cpu_cores"] = raw.get("physical_cpu_cores")
        metrics["logical_cpu_cores"] = raw.get("logical_cpu_cores")
        metrics["cpu_cores"] = metrics["logical_cpu_cores"] or raw.get("cpu_cores")
        metrics["device_memory_gb"] = raw.get("device_memory_gb")
        metrics["online"] = raw.get("online")
        metrics["page_load_ms"] = raw.get("page_load_ms")
        metrics["local_app_available"] = raw.get("local_app_available", False)
        metrics["local_app_error"] = raw.get("local_app_error")
        metrics["local_app_response"] = raw.get("local_app_response")
        if isinstance(raw.get("local_app_response"), dict):
            local_app_response = raw["local_app_response"]
            local_metrics = local_app_response.get("metrics")
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
                    "logical_cpu_cores",
                    "browser_hardware_concurrency",
                    "edge_running",
                ):
                    if metrics.get(key) in (None, []):
                        metrics[key] = local_metrics.get(key)
                metrics["cpu_cores"] = metrics.get("logical_cpu_cores") or metrics.get(
                    "cpu_cores"
                )
            metrics["tool_candidates"] = local_app_response.get("tools", [])
            metrics["remediation_actions"] = local_app_response.get("actions", [])
            metrics["edge_running"] = bool(metrics.get("edge_running")) or any(
                action.get("id") == "stop_edge" and action.get("available")
                for action in metrics["remediation_actions"]
                if isinstance(action, dict)
            )
            metrics["diagnostic_recommendation"] = local_app_response.get(
                "recommendation"
            )
            metrics["local_app_summary"] = local_app_response.get("summary")
        if metrics.get("logical_cpu_cores") is None:
            metrics["logical_cpu_cores"] = metrics.get("cpu_cores")
        metrics["cpu_cores"] = metrics.get("logical_cpu_cores") or metrics.get(
            "cpu_cores"
        )
    return metrics
