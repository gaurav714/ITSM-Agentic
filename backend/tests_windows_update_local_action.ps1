$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $repoRoot "backend"
$python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

@'
from app.workflows.windows_update_failure.workflow import (
    WindowsUpdateFailureWorkflow,
    _should_offer_ticket,
)

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

pending_ticket_missing_checks = {
    "session_id": "pending-ticket-missing-checks",
    "workflow": "windows_update_failure",
    "state": "awaiting_agent_followup",
    "windows_update_checks_discussed": ["internet_ok", "vpn_connected"],
    "windows_update_ticket_requested": True,
    "windows_update_ticket_request_message": "internet connection is stable, please create a ticket",
    "windows_update_tool_results": [],
}
assert not _should_offer_ticket(pending_ticket_missing_checks, "has enough disk space")

pending_ticket_ready = {
    "session_id": "pending-ticket-ready",
    "workflow": "windows_update_failure",
    "state": "awaiting_agent_followup",
    "windows_update_checks_discussed": [
        "vpn_connected",
        "internet_ok",
        "restarted",
        "disk_space_checked",
    ],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": False,
    "windows_update_tool_results": [],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "",
    "windows_update_ticket_requested": True,
    "windows_update_ticket_request_message": "internet connection is stable, please create a ticket",
}
resp = wf.handle(pending_ticket_ready, "has enough disk space")
assert resp.state == "awaiting_ticket_confirmation", resp
assert resp.cards[0].kind == "ticket_draft", resp.cards
assert "local actions" not in resp.message.lower(), resp.message
assert "please create a ticket" in resp.cards[0].data["description"], resp.cards[0].data["description"]
assert pending_ticket_ready["windows_update_ticket_requested"] is False, pending_ticket_ready

terminal = {
    "session_id": "terminal-ticket",
    "workflow": "windows_update_failure",
    "state": "awaiting_agent_followup",
    "windows_update_checks_discussed": [
        "vpn_connected",
        "internet_ok",
        "restarted",
        "disk_space_checked",
    ],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": True,
    "windows_update_tool_results": [
        {
            "session_id": "terminal-ticket",
            "action": "collect_windows_update_status",
            "status": "complete",
            "message": "Collected Windows Update service status.",
            "service_statuses": {
                "wuauserv": {"name": "wuauserv", "status": "running", "start_type": "manual"},
                "bits": {"name": "bits", "status": "running", "start_type": "manual"},
            },
            "pending_reboot": False,
            "errors": [],
        },
        {
            "session_id": "terminal-ticket",
            "action": "open_windows_update_settings",
            "status": "complete",
            "message": "Opened Windows Update settings.",
            "errors": [],
        },
    ],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "",
}
resp = wf.handle(terminal, "it is still failing after all that")
assert resp.state == "awaiting_ticket_confirmation", resp
assert resp.cards[0].kind == "ticket_draft", resp.cards
assert resp.cards[0].data["category"] == "Windows Update", resp.cards[0].data
assert "wuauserv=running" in resp.cards[0].data["description"], resp.cards[0].data["description"]
assert terminal["ticket_draft"]["title"].startswith("Windows Update failure - "), terminal["ticket_draft"]

resp = wf.handle(terminal, "yes please create it")
assert resp.state == "complete", resp
assert resp.cards[0].kind == "ticket_created", resp.cards
assert terminal["ticket_id"].startswith("INC"), terminal

cancel = {
    "session_id": "terminal-cancel",
    "workflow": "windows_update_failure",
    "state": "awaiting_ticket_confirmation",
    "ticket_draft": {
        "session_id": "terminal-cancel",
        "title": "Windows Update failure - LOCAL-ENDPOINT",
        "description": "Windows Update still fails.",
        "category": "Windows Update",
        "priority": "Medium",
        "device_name": "LOCAL-ENDPOINT",
        "diagnostic_id": None,
    },
    "windows_update_checks_discussed": [
        "vpn_connected",
        "internet_ok",
        "restarted",
        "disk_space_checked",
    ],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": True,
    "windows_update_tool_results": [],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "",
}
resp = wf.handle(cancel, "no")
assert resp.state == "idle", resp
assert cancel["ticket_draft"] is None, cancel

unreachable = {
    "session_id": "terminal-unreachable",
    "workflow": "windows_update_failure",
    "state": "awaiting_agent_followup",
    "windows_update_checks_discussed": [
        "vpn_connected",
        "internet_ok",
        "restarted",
        "disk_space_checked",
    ],
    "windows_update_agent_trace": [],
    "windows_update_last_decision": None,
    "windows_update_access_approved": True,
    "windows_update_tool_results": [
        {
            "session_id": "terminal-unreachable",
            "action": "collect_windows_update_status",
            "status": "failed",
            "message": "Unable to contact the local app diagnostic server.",
            "errors": ["local_app_unreachable"],
        },
    ],
    "windows_update_current_check": "",
    "windows_update_pending_tool": "",
}
resp = wf.handle(unreachable, "windows update is still not working")
assert resp.state == "awaiting_ticket_confirmation", resp
assert resp.cards[0].kind == "ticket_draft", resp.cards

print("Windows Update local action regression checks passed.")
'@ | & $python -B -
