"""Read-only local diagnostic tools.

The functions here are intentionally small and allowlisted. The assistant can
select from them, but it cannot execute arbitrary commands.
"""

from __future__ import annotations

import os
import platform
import shutil
from typing import Any, Dict, Iterable, List

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None

from app.schemas import DiagnosticContext, ToolResult


def search_tools(query: str) -> list[str]:
    terms = set((query or "").lower().split())
    selected = ["system_profile", "disk_snapshot"]

    if terms & {"slow", "sluggish", "performance", "crawling", "unresponsive"}:
        selected.extend(["cpu_memory_snapshot", "process_snapshot"])

    return _dedupe(selected)


def run_tool(name: str, context: DiagnosticContext) -> ToolResult:
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
        description="Tool is not allowlisted by this local diagnostic assistant.",
        result={},
    )


def merge_metrics(results: Iterable[ToolResult]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    for tool in results:
        for key, value in tool.result.items():
            if value not in (None, [], ""):
                metrics[key] = value
    return metrics


def is_edge_running() -> bool:
    if psutil is None:
        return False
    return any(_is_edge_process(proc) for proc in psutil.process_iter(["name"]))


def stop_edge_processes() -> Dict[str, Any]:
    if psutil is None:
        return {
            "status": "unavailable",
            "message": "psutil is not installed, so Edge cannot be stopped.",
            "stopped_processes": [],
            "errors": [],
        }

    edge_processes = [proc for proc in psutil.process_iter(["name"]) if _is_edge_process(proc)]
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

    gone, alive = psutil.wait_procs(edge_processes, timeout=3)
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


def _system_profile(context: DiagnosticContext) -> ToolResult:
    browser_metrics = context.browser_metrics or {}
    result = {
        "hostname": platform.node() or None,
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_cores": os.cpu_count() or browser_metrics.get("cpu_cores"),
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
        result={"top_processes": top, "edge_running": is_edge_running()},
    )


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
