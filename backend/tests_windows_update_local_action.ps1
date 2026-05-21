$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $repoRoot "backend"
$python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

@'
from app.workflows.windows_update_failure.workflow import WindowsUpdateFailureWorkflow

wf = WindowsUpdateFailureWorkflow()

session = {
    "workflow": "windows_update_failure",
    "state": "awaiting_access_approval",
    "windows_update_checks_discussed": ["vpn_connected", "internet_ok"],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": False,
    "windows_update_tool_results": [],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "",
}
resp = wf.handle(session, "yes you have the permission")
assert resp.state == "awaiting_tool_result", resp
assert resp.metadata["trigger_local_app_action"]["action"] == "collect_windows_update_status", resp.metadata
assert session["windows_update_pending_tool"] == "collect_windows_update_status", session

session["local_action_result"] = {
    "session_id": "direct-success",
    "action": "collect_windows_update_status",
    "status": "complete",
    "message": "Collected Windows Update service status.",
    "service_statuses": {
        "wuauserv": {"name": "wuauserv", "status": "running", "start_type": "manual"},
        "bits": {"name": "bits", "status": "running", "start_type": "manual"},
    },
    "pending_reboot": False,
    "errors": [],
}
resp = wf.handle(session, "local app action complete")
assert resp.state == "awaiting_agent_followup", resp
assert "trigger_local_app_action" not in resp.metadata, resp.metadata
assert "wuauserv=running" in resp.message, resp.message
assert "Pending reboot: no." in resp.message, resp.message
assert session["windows_update_pending_tool"] == "", session

failed = {
    "workflow": "windows_update_failure",
    "state": "awaiting_tool_result",
    "windows_update_checks_discussed": ["vpn_connected", "internet_ok"],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": True,
    "windows_update_tool_results": [],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "collect_windows_update_status",
    "local_action_result": {
        "session_id": "direct-failed",
        "action": "collect_windows_update_status",
        "status": "failed",
        "message": "Unable to contact the local app diagnostic server.",
        "errors": ["local_app_unreachable"],
    },
}
resp = wf.handle(failed, "local app action failed")
assert "could not reach the local diagnostic app" in resp.message, resp.message
assert "trigger_local_app_action" not in resp.metadata, resp.metadata

pending = {
    "workflow": "windows_update_failure",
    "state": "awaiting_tool_result",
    "windows_update_checks_discussed": ["vpn_connected", "internet_ok"],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": True,
    "windows_update_tool_results": [],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "collect_windows_update_status",
}
resp = wf.handle(pending, "run local diagnostic app now")
assert "trigger_local_app_action" not in resp.metadata, resp.metadata
assert "already sent" in resp.message, resp.message

print("Windows Update local action regression checks passed.")
'@ | & $python -B -
