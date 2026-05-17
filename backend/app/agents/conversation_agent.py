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
    return workflow_id == "windows_update_failure" and state in {
        "awaiting_fix_result",
        "awaiting_access_approval",
        "awaiting_settings_action",
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
    ):
        session.pop(key, None)
    session["state"] = "idle"
