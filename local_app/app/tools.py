"""Read-only local diagnostic tools.

The functions here are intentionally small and allowlisted. The assistant can
select from them, but it cannot execute arbitrary commands.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import time
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
        description="Tool is not allowlisted by this local diagnostic app.",
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


def open_windows_update_settings() -> Dict[str, Any]:
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


def collect_windows_update_status() -> Dict[str, Any]:
    if platform.system().lower() != "windows":
        return {
            "status": "unsupported",
            "message": "Windows Update status collection is only supported on Windows.",
            "service_statuses": {},
            "pending_reboot": None,
            "errors": ["unsupported_os"],
        }

    service_names = ["wuauserv", "bits", "cryptsvc", "usosvc"]
    services = {name: _windows_service_status(name) for name in service_names}
    pending_reboot = _windows_pending_reboot()
    unavailable = [
        name for name, data in services.items() if data.get("status") == "unknown"
    ]
    status = "partial" if unavailable else "complete"
    return {
        "status": status,
        "message": "Collected Windows Update service status.",
        "service_statuses": services,
        "pending_reboot": pending_reboot,
        "errors": [f"Unable to read service: {name}" for name in unavailable],
    }


def run_powershell_task(command: str, timeout_seconds: int = 15) -> Dict[str, Any]:
    command = (command or "").strip()
    if not command:
        return {
            "status": "rejected",
            "message": "PowerShell command is required.",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "duration_ms": 0,
            "needs_elevation": False,
            "errors": ["missing_command"],
        }

    if platform.system().lower() != "windows":
        return {
            "status": "unsupported",
            "message": "PowerShell task execution is only supported on Windows.",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "duration_ms": 0,
            "needs_elevation": False,
            "errors": ["unsupported_os"],
        }

    timeout = max(3, min(int(timeout_seconds or 15), 60))
    start = time.monotonic()
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout = _truncate_output(completed.stdout)
        stderr = _truncate_output(completed.stderr)
        needs_elevation = _looks_like_elevation_error(stdout, stderr)
        if needs_elevation:
            status = "needs_elevation"
            message = "The command appears to require administrator privileges."
        elif completed.returncode == 0:
            status = "complete"
            message = "PowerShell task completed."
        else:
            status = "failed"
            message = f"PowerShell task failed with exit code {completed.returncode}."
        return {
            "status": status,
            "message": message,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "needs_elevation": needs_elevation,
            "errors": [] if completed.returncode == 0 else [stderr or message],
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "timeout",
            "message": f"PowerShell task timed out after {timeout} seconds.",
            "stdout": _truncate_output(exc.stdout or ""),
            "stderr": _truncate_output(exc.stderr or ""),
            "exit_code": None,
            "duration_ms": duration_ms,
            "needs_elevation": False,
            "errors": ["timeout"],
        }
    except FileNotFoundError:
        return {
            "status": "failed",
            "message": "powershell.exe was not found on this system.",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "needs_elevation": False,
            "errors": ["powershell_not_found"],
        }
    except Exception as exc:
        return {
            "status": "failed",
            "message": "Unable to run PowerShell task.",
            "stdout": "",
            "stderr": str(exc),
            "exit_code": None,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "needs_elevation": _looks_like_elevation_error("", str(exc)),
            "errors": [str(exc)],
        }


def _system_profile(context: DiagnosticContext) -> ToolResult:
    browser_metrics = context.browser_metrics or {}
    logical_cpu_cores = _logical_cpu_count()
    physical_cpu_cores = _physical_cpu_count()
    result = {
        "hostname": platform.node() or None,
        "os": platform.platform(),
        "machine": platform.machine(),
        "physical_cpu_cores": physical_cpu_cores,
        "logical_cpu_cores": logical_cpu_cores,
        "browser_hardware_concurrency": browser_metrics.get(
            "browser_hardware_concurrency"
        )
        or browser_metrics.get("cpu_cores"),
        "cpu_cores": logical_cpu_cores or browser_metrics.get("cpu_cores"),
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


def _physical_cpu_count() -> int | None:
    if psutil is None:
        return None
    return psutil.cpu_count(logical=False)


def _logical_cpu_count() -> int | None:
    if psutil is not None:
        return psutil.cpu_count(logical=True) or os.cpu_count()
    return os.cpu_count()


def _windows_service_status(service_name: str) -> Dict[str, Any]:
    if psutil is not None:
        try:
            service = psutil.win_service_get(service_name)
            info = service.as_dict()
            return {
                "name": service_name,
                "display_name": info.get("display_name"),
                "status": info.get("status"),
                "start_type": info.get("start_type"),
            }
        except Exception as exc:
            return {"name": service_name, "status": "unknown", "error": str(exc)}

    try:
        result = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            timeout=3,
            shell=False,
        )
        output = result.stdout + result.stderr
        match = re.search(r"STATE\s*:\s*\d+\s+(\w+)", output)
        return {
            "name": service_name,
            "status": (match.group(1).lower() if match else "unknown"),
            "raw": output.strip()[:500],
        }
    except Exception as exc:
        return {"name": service_name, "status": "unknown", "error": str(exc)}


def _windows_pending_reboot() -> bool | None:
    try:
        import winreg

        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
        ]
        for key in keys:
            try:
                handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key)
                winreg.CloseKey(handle)
                return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return None


def _truncate_output(value: str, limit: int = 12000) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _looks_like_elevation_error(stdout: str, stderr: str) -> bool:
    text = f"{stdout}\n{stderr}".lower()
    patterns = (
        "access is denied",
        "access denied",
        "administrator privileges",
        "run as administrator",
        "requires elevation",
        "requested operation requires elevation",
        "unauthorizedaccessexception",
        "permission denied",
    )
    return any(pattern in text for pattern in patterns)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
