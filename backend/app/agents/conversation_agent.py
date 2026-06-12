"""Top-level conversation agent.

Routes every user message:
  1. If the user clearly asks for a different workflow, switch workflows.
  2. If the session already owns an active workflow, hand the message to it.
  3. Otherwise classify intent and dispatch to the matching workflow,
     or return a generic fallback response.
"""

import re
from typing import Any, Dict

from app.agents.intent_router import classify_intent
from app.memory.session_store import session_store
from app.models.schemas import AgentMessageResponse
from app.services.workflow_registry import get_workflow, list_workflows


def handle_user_message(
    session_id: str, message: str, forced_workflow: str | None = None
) -> AgentMessageResponse:
    session: Dict[str, Any] = session_store.get(session_id)
    session["session_id"] = session_id
    session_store.append_message(session_id, "user", message)

    workflow_id = forced_workflow or session.get("workflow")
    current_workflow = session.get("workflow")
    current_state = session.get("state")

    # Completed onboarding often continues in the same chat with the next
    # employee's details. Keep that message inside onboarding so the workflow
    # can clear prior employee state and restart cleanly.
    if (
        not forced_workflow
        and session.get("workflow") == "new_employee_onboarding"
        and session.get("state") == "complete"
        and _looks_like_onboarding_followup(message)
    ):
        workflow_id = "new_employee_onboarding"

    # Browser/local-app handoff messages are internal protocol markers, not
    # new user intent. Keep them in the workflow that requested the handoff.
    elif not forced_workflow and current_workflow and _is_protocol_message(message):
        workflow_id = current_workflow

    # Supervisor routing: while a workflow is active, a clear intent for a
    # different workflow should switch context instead of being interpreted as
    # the current workflow's next field.
    elif not forced_workflow and current_workflow and current_state not in (
        None,
        "idle",
        "complete",
    ):
        if _is_sticky_workflow_turn(current_workflow, current_state):
            workflow_id = current_workflow
        else:
            requested_workflow = classify_intent(message)
            if requested_workflow not in ("unknown", current_workflow):
                _reset_workflow_context(session)
                workflow_id = requested_workflow

    # If there's no active workflow, classify intent.
    elif not workflow_id or session.get("state") in (None, "idle", "complete"):
        workflow_id = forced_workflow or classify_intent(message)

    workflow = get_workflow(workflow_id) if workflow_id else None

    if workflow is None or workflow_id == "unknown":
        response = AgentMessageResponse(
            message=(
                "I'm an IT helpdesk assistant. I can help with: "
                + ", ".join(w["title"] for w in list_workflows())
                + ". Try: 'My system is slow'."
            ),
            requires_input=True,
        )
        session_store.append_message(session_id, "assistant", response.message)
        return response

    response = workflow.handle(session, message)
    session_store.append_message(session_id, "assistant", response.message)
    return response


def _looks_like_onboarding_followup(message: str) -> bool:
    text = (message or "").lower()
    return bool(
        re.search(
            r"\b(full\s+name|email|work\s+email|department|dept|role|job\s+title|onboard|onboarding|new\s+(user|employee|hire))\b",
            text,
        )
    )


def _is_sticky_workflow_turn(workflow_id: str, state: str | None) -> bool:
    """Keep short in-workflow replies away from global intent routing."""
    if workflow_id == "local_system_agent":
        return state in {"awaiting_request", "awaiting_tool_result"}
    if workflow_id == "system_slow_diagnostics":
        return state in {
            "awaiting_browser_diagnostics",
            "awaiting_remediation_confirmation",
            "awaiting_remediation_action",
            "awaiting_confirmation",
        }
    return workflow_id == "windows_update_failure" and state in {
        "awaiting_fix_result",
        "awaiting_agent_followup",
        "awaiting_access_approval",
        "awaiting_settings_action",
        "awaiting_tool_result",
    }


def _reset_workflow_context(session: Dict[str, Any]) -> None:
    for key in (
        "workflow",
        "state",
        "device_name",
        "diagnostic_id",
        "diagnostic",
        "ticket_draft",
        "ticket_id",
        "employee",
        "access_groups",
        "onboarding_id",
        "onboarding_result",
        "existing_identity_user",
        "windows_update_checks_tried",
        "windows_update_checks_discussed",
        "windows_update_agent_trace",
        "windows_update_last_decision",
        "windows_update_access_approved",
        "windows_update_tool_results",
        "windows_update_current_check",
        "windows_update_llm_called",
        "windows_update_agent_error",
        "local_system_pending_task",
        "local_action_result",
    ):
        session.pop(key, None)
    session["state"] = "idle"


def _is_protocol_message(message: str) -> bool:
    return (message or "").strip().lower() in {
        "browser diagnostics ready",
        "local app action complete",
        "local app action failed",
    }
