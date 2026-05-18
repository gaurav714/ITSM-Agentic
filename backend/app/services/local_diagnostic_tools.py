"""Backend-native allowlisted local diagnostic and action tools."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


class DiagnosticContext(BaseModel):
    session_id: Optional[str] = None
    device_name: Optional[str] = None
    diagnostic_id: Optional[str] = None
    browser_metrics: Dict[str, Any] = Field(default_factory=dict)


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


class ActionExecutionResponse(BaseModel):
    action: str
    status: str
    message: str
    stopped_processes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    opened_uri: Optional[str] = None


def diagnose_local_system(
    query: str = "system is slow", context: Optional[Dict[str, Any]] = None
) -> DiagnosticSearchResponse:
    """Run allowlisted backend-local diagnostics for the current workstation."""
    diagnostic_context = DiagnosticContext(**(context or {}))
    tool_names = _search_tools(query)
    tool_results = [_run_tool(name, diagnostic_context) for name in tool_names]
    metrics = _merge_metrics(tool_results)
    summary, recommendation, confidence = _summarize(metrics)
    return DiagnosticSearchResponse(
        summary=summary,
        recommendation=recommendation,
        tools=tool_results,
        actions=_actions_for_metrics(metrics),
        metrics=metrics,
        confidence=confidence,
    )


def execute_local_action(
    action: str, context: Optional[Dict[str, Any]] = None
) -> ActionExecutionResponse:
    """Execute one explicitly allowlisted local action."""
    _ = DiagnosticContext(**(context or {}))

    if action == "stop_edge":
        result = _stop_edge_processes()
        return ActionExecutionResponse(
            action="stop_edge",
            status=result["status"],
            message=result["message"],
            stopped_processes=result["stopped_processes"],
            errors=result["errors"],
        )

    if action == "open_windows_update_settings":
        result = _open_windows_update_settings()
        return ActionExecutionResponse(
            action="open_windows_update_settings",
            status=result["status"],
            message=result["message"],
            errors=result["errors"],
            opened_uri=result["opened_uri"],
        )

    return ActionExecutionResponse(
        action=action,
        status="rejected",
        message="This backend action is not allowlisted.",
        errors=["unknown_action"],
    )


def _search_tools(query: str) -> list[str]:
    terms = set((query or "").lower().split())
    selected = ["system_profile", "disk_snapshot"]

    if terms & {"slow", "sluggish", "performance", "crawling", "unresponsive"}:
        selected.extend(["cpu_memory_snapshot", "process_snapshot"])

    return _dedupe(selected)


def _run_tool(name: str, context: DiagnosticContext) -> ToolResult:
    if name == "system_profile":
        return _system_profile(context)
    if name == "disk_snapshot":
        return _disk_snapshot()
    if name == "cpu_memory_snapshot":
        return _cpu_memory_snapshot()
    if name == "process_snapshot":
        return _process_snapshot()

    return ToolResult(
        name=name,
        status="skipped",
        description="Tool is not allowlisted by the backend diagnostic service.",
        result={},
    )


def _merge_metrics(results: Iterable[ToolResult]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    for tool_result in results:
        for key, value in tool_result.result.items():
            if value not in (None, [], ""):
                metrics[key] = value
    return metrics


def _actions_for_metrics(metrics: dict) -> list[ActionOption]:
    edge_running = bool(metrics.get("edge_running")) or _is_edge_running()
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
        "Install optional metrics support or collect browser-only diagnostics.",
        0.4,
    )


def _system_profile(context: DiagnosticContext) -> ToolResult:
    browser_metrics = context.browser_metrics or {}
    physical_cpu_cores = psutil.cpu_count(logical=False) if psutil is not None else None
    logical_cpu_processors = (
        psutil.cpu_count(logical=True) if psutil is not None else os.cpu_count()
    )
    result = {
        "hostname": platform.node() or None,
        "os": platform.platform(),
        "machine": platform.machine(),
        "physical_cpu_cores": physical_cpu_cores,
        "logical_cpu_processors": logical_cpu_processors,
        "cpu_cores": physical_cpu_cores or logical_cpu_processors,
        "browser_reported_cpu_cores": browser_metrics.get("cpu_cores"),
        "device_memory_gb": browser_metrics.get("device_memory_gb"),
    }
    return ToolResult(
        name="system_profile",
        status="complete",
        description="Collected basic local system profile.",
        result=result,
    )


def _disk_snapshot() -> ToolResult:
    try:
        usage = shutil.disk_usage(os.path.abspath(os.sep))
        free_gb = round(usage.free / (1024**3), 1)
        total_gb = round(usage.total / (1024**3), 1)
        result = {"disk_free_gb": free_gb, "disk_total_gb": total_gb}
        status = "complete"
    except Exception as exc:
        result = {"error": str(exc)}
        status = "failed"

    return ToolResult(
        name="disk_snapshot",
        status=status,
        description="Collected free disk space for the system drive.",
        result=result,
    )


def _cpu_memory_snapshot() -> ToolResult:
    if psutil is None:
        return ToolResult(
            name="cpu_memory_snapshot",
            status="unavailable",
            description="psutil is not installed, so CPU and memory usage were not available.",
            result={},
        )

    result = {
        "cpu_pct": psutil.cpu_percent(interval=0.25),
        "memory_pct": psutil.virtual_memory().percent,
    }
    return ToolResult(
        name="cpu_memory_snapshot",
        status="complete",
        description="Collected current CPU and memory utilization.",
        result=result,
    )


def _process_snapshot() -> ToolResult:
    if psutil is None:
        return ToolResult(
            name="process_snapshot",
            status="unavailable",
            description="psutil is not installed, so top processes were not available.",
            result={},
        )

    processes: List[tuple[float, str]] = []
    for proc in psutil.process_iter(["name", "memory_percent"]):
        try:
            name = proc.info.get("name") or f"pid-{proc.pid}"
            processes.append((float(proc.info.get("memory_percent") or 0.0), name))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top = [name for _, name in sorted(processes, reverse=True)[:5]]
    return ToolResult(
        name="process_snapshot",
        status="complete",
        description="Collected top processes by memory usage.",
        result={"top_processes": top, "edge_running": _is_edge_running()},
    )


def _is_edge_running() -> bool:
    if psutil is None:
        return False
    return any(_is_edge_process(proc) for proc in psutil.process_iter(["name"]))


def _stop_edge_processes() -> Dict[str, Any]:
    if psutil is None:
        return {
            "status": "unavailable",
            "message": "psutil is not installed, so Edge cannot be stopped.",
            "stopped_processes": [],
            "errors": [],
        }

    edge_processes = [
        proc for proc in psutil.process_iter(["name"]) if _is_edge_process(proc)
    ]
    if not edge_processes:
        return {
            "status": "not_running",
            "message": "Microsoft Edge was not running.",
            "stopped_processes": [],
            "errors": [],
        }

    stopped: list[str] = []
    errors: list[str] = []
    for proc in edge_processes:
        try:
            name = proc.info.get("name") or f"pid-{proc.pid}"
            proc.terminate()
            stopped.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            errors.append(f"{getattr(proc, 'pid', 'unknown')}: {exc}")

    _, alive = psutil.wait_procs(edge_processes, timeout=3)
    for proc in alive:
        try:
            name = proc.info.get("name") or f"pid-{proc.pid}"
            proc.kill()
            if name not in stopped:
                stopped.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            errors.append(f"{getattr(proc, 'pid', 'unknown')}: {exc}")

    status = "complete" if stopped and not errors else "partial" if stopped else "failed"
    return {
        "status": status,
        "message": f"Stopped {len(stopped)} Microsoft Edge process(es).",
        "stopped_processes": stopped,
        "errors": errors,
    }


def _open_windows_update_settings() -> Dict[str, Any]:
    uri = "ms-settings:windowsupdate"
    if platform.system().lower() != "windows":
        return {
            "status": "unsupported",
            "message": "Opening Windows Update settings is only supported on Windows.",
            "opened_uri": uri,
            "errors": ["unsupported_os"],
        }

    try:
        os.startfile(uri)  # type: ignore[attr-defined]
        return {
            "status": "complete",
            "message": "Opened Windows Update settings.",
            "opened_uri": uri,
            "errors": [],
        }
    except Exception as exc:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
            return {
                "status": "complete",
                "message": "Opened Windows Update settings.",
                "opened_uri": uri,
                "errors": [],
            }
        except Exception as fallback_exc:
            return {
                "status": "failed",
                "message": "Unable to open Windows Update settings.",
                "opened_uri": uri,
                "errors": [str(exc), str(fallback_exc)],
            }


def _is_edge_process(proc) -> bool:
    try:
        name = (proc.info.get("name") or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
        return False
    return name in {"msedge.exe", "microsoftedge.exe", "edge.exe"}


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
