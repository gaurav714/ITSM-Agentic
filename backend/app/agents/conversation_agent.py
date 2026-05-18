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

    # Supervisor routing: while a workflow is active, a clear intent for a
    # different workflow should switch context instead of being interpreted as
    # the current workflow's next field.
    elif not forced_workflow and current_workflow and current_state not in (
        None,
        "idle",
        "complete",
    ):
        requested_workflow = classify_intent(message)
        if (
            requested_workflow not in ("unknown", current_workflow)
            and _looks_like_explicit_workflow_switch(message, requested_workflow)
        ):
            _reset_workflow_context(session)
            workflow_id = requested_workflow
        else:
            workflow_id = current_workflow

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
    if response.workflow:
        session["workflow"] = response.workflow
    if response.state:
        session["state"] = response.state
    if response.metadata:
        session["last_agent_metadata"] = response.metadata
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


def _looks_like_explicit_workflow_switch(
    message: str, requested_workflow: str | None
) -> bool:
    """Return True only when the user is asking to start another workflow."""
    if not message or not requested_workflow or requested_workflow == "unknown":
        return False

    text = message.lower()
    action_pattern = (
        r"\b(start|open|switch|change|new|request|create|begin|launch)\b"
        r"|\bhelp\s+me\s+with\b"
        r"|\bi\s+need\s+(?:a|an)?\s*\w*"
    )
    if not re.search(action_pattern, text):
        return False

    workflow_terms = {
        "system_slow_diagnostics": (
            "system slow",
            "slow diagnostics",
            "performance",
            "lagging",
        ),
        "new_employee_onboarding": (
            "onboarding",
            "new employee",
            "new hire",
            "joiner",
        ),
        "windows_update_failure": ("windows update", "update failure", "patch"),
        "password_reset": ("password reset", "reset password", "forgot password"),
        "vpn_access": ("vpn access", "remote access", "vpn request"),
        "software_install": ("software install", "software installation", "install software"),
        "account_unlock": ("account unlock", "unlock account", "locked account"),
        "ticket_status": ("ticket status", "status of ticket", "lookup ticket"),
        "application_outage": ("application outage", "app outage", "service down"),
    }
    return any(term in text for term in workflow_terms.get(requested_workflow, ()))


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
    ):
        session.pop(key, None)
    session["state"] = "idle"
