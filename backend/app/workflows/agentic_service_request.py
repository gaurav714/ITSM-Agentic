"""Shared mock-functional agentic service request workflows."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional

from app.adapters.identity.mock_identity_adapter import mock_identity_adapter
from app.adapters.ticketing.mock_ticket_adapter import mock_ticket_adapter
from app.models.schemas import AgentMessageResponse, TicketDraft, UICard
from app.services.ticket_service import create_ticket
from app.services.workflow_turn_agent import agent_metadata, choose_workflow_tool
from app.workflows.base import BaseWorkflow

_AFFIRMATIVE = {
    "yes",
    "y",
    "confirm",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "submit",
    "create",
    "do it",
    "please do",
}
_NEGATIVE = {"no", "n", "cancel", "stop", "abort", "not now", "never mind"}
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_TICKET_RE = re.compile(r"\b(?:INC|REQ|OUT)[A-Z0-9]{6,12}\b", re.IGNORECASE)

_SOFTWARE_CATALOG = {
    "chrome": {"name": "Google Chrome", "licensed": True, "approval_required": False},
    "vscode": {"name": "Visual Studio Code", "licensed": True, "approval_required": False},
    "visual studio code": {
        "name": "Visual Studio Code",
        "licensed": True,
        "approval_required": False,
    },
    "figma": {"name": "Figma", "licensed": True, "approval_required": True},
    "photoshop": {"name": "Adobe Photoshop", "licensed": False, "approval_required": True},
    "power bi": {"name": "Power BI", "licensed": True, "approval_required": True},
}

_OUTAGE_REPORTS: Dict[str, Dict[str, Any]] = {}


@dataclass
class ServiceWorkflowConfig:
    workflow_id: str
    title: str
    agent_name: str
    required_fields: list[str]
    field_labels: Dict[str, str]
    initial_prompt: str
    confirmation_prompt: str
    category: str
    priority: str = "Medium"
    extractor: Optional[Callable[[str, Dict[str, Any]], Dict[str, str]]] = None
    validator: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    completion: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None
    tool_options: Dict[str, str] = field(default_factory=dict)


class AgenticServiceRequestWorkflow(BaseWorkflow):
    active = True

    def __init__(self, config: ServiceWorkflowConfig) -> None:
        self.config = config
        self.workflow_id = config.workflow_id
        self.title = config.title

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        state = session.get("state", "idle")
        msg = (user_message or "").strip()
        if session.get("workflow") != self.workflow_id:
            self._reset(session)
            state = "idle"

        selected_tool = self._choose_tool(session, state, msg)
        session["last_service_agent_tool"] = selected_tool

        if state in ("idle", None, "awaiting_details"):
            details = {
                **(session.get("service_request_details") or {}),
                **self._extract_details(msg, session),
            }
            session["service_request_details"] = details
            missing = self._missing(details)
            if missing:
                return self._ask_for_details(missing, selected_tool)
            return self._confirm_request(session, details, selected_tool)

        if state == "awaiting_confirmation":
            decision = _classify_confirmation(msg)
            if decision == "cancel":
                session["state"] = "idle"
                return AgentMessageResponse(
                    message=f"{self.title} request cancelled. No changes were made.",
                    workflow=self.workflow_id,
                    state="idle",
                    metadata=self._metadata("cancel_request"),
                    requires_input=False,
                )
            if decision != "confirm":
                return AgentMessageResponse(
                    message="Please reply 'yes' to submit this request or 'no' to cancel.",
                    workflow=self.workflow_id,
                    state="awaiting_confirmation",
                    metadata=self._metadata("confirm_request"),
                )
            return self._complete(session, selected_tool)

        if state == "complete":
            self._reset(session)
            return self.handle(session, msg)

        return self._ask_for_details(self.config.required_fields, selected_tool)

    def _reset(self, session: Dict[str, Any]) -> None:
        session["workflow"] = self.workflow_id
        session["state"] = "awaiting_details"
        for key in (
            "service_request_details",
            "service_request_validation",
            "service_request_ticket",
        ):
            session.pop(key, None)

    def _extract_details(self, msg: str, session: Dict[str, Any]) -> Dict[str, str]:
        if self.config.extractor:
            return self.config.extractor(msg, session)
        return _extract_generic_details(msg, self.config.required_fields)

    def _missing(self, details: Dict[str, Any]) -> list[str]:
        return [field for field in self.config.required_fields if not details.get(field)]

    def _ask_for_details(
        self, missing: Iterable[str], selected_tool: str
    ) -> AgentMessageResponse:
        labels = [self.config.field_labels.get(field, field) for field in missing]
        message = self.config.initial_prompt
        if labels:
            message += "\n\nI still need: " + ", ".join(labels) + "."
        return AgentMessageResponse(
            message=message,
            workflow=self.workflow_id,
            state="awaiting_details",
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "collect_details",
                        "missing": labels,
                    },
                )
            ],
            metadata=self._metadata(selected_tool or "ask_missing_details"),
        )

    def _confirm_request(
        self, session: Dict[str, Any], details: Dict[str, Any], selected_tool: str
    ) -> AgentMessageResponse:
        validation = self.config.validator(details) if self.config.validator else {}
        session["service_request_validation"] = validation
        session["state"] = "awaiting_confirmation"
        summary = _format_details(details)
        validation_text = validation.get("message")
        message = f"{self.config.confirmation_prompt}\n\n{summary}"
        if validation_text:
            message += f"\n\n{validation_text}"
        message += "\n\nReply 'yes' to submit or 'no' to cancel."
        return AgentMessageResponse(
            message=message,
            workflow=self.workflow_id,
            state="awaiting_confirmation",
            cards=[
                UICard(
                    kind="confirmation",
                    data={
                        "title": self.title,
                        "action": "submit_request",
                        "details": details,
                        "validation": validation,
                    },
                )
            ],
            metadata=self._metadata(selected_tool or "confirm_request"),
        )

    def _complete(
        self, session: Dict[str, Any], selected_tool: str
    ) -> AgentMessageResponse:
        details = session.get("service_request_details") or {}
        validation = session.get("service_request_validation") or {}
        if self.config.completion:
            completed = self.config.completion(self.workflow_id, details, validation)
        else:
            completed = _create_service_ticket(self.config, details, validation)
        session["service_request_ticket"] = completed
        session["state"] = "complete"
        return AgentMessageResponse(
            message=completed["message"],
            workflow=self.workflow_id,
            state="complete",
            cards=[UICard(kind="ticket_created", data=completed["ticket"])],
            metadata=self._metadata(selected_tool or "submit_request"),
            requires_input=False,
        )

    def _choose_tool(self, session: Dict[str, Any], state: str, msg: str) -> str:
        options = self.config.tool_options or {
            "ask_missing_details": "Ask for missing details needed by the workflow.",
            "validate_request": "Validate the request using mock backend tools.",
            "confirm_request": "Ask for explicit confirmation before mutation or ticket creation.",
            "submit_request": "Submit the confirmed mock-functional request.",
            "cancel_request": "Cancel the request.",
        }
        selected = choose_workflow_tool(
            agent_name=self.config.agent_name,
            system_prompt=(
                f"You are the {self.title} workflow agent. Choose exactly one "
                "allowlisted tool for this turn. Never submit or mutate anything "
                "unless the user explicitly confirmed."
            ),
            objective={
                "session_state": state,
                "user_message": msg,
                "known_details": session.get("service_request_details") or {},
                "required_fields": self.config.required_fields,
            },
            tool_options=options,
        )
        if selected:
            return selected["tool"]
        if state == "awaiting_confirmation":
            return "submit_request" if _classify_confirmation(msg) == "confirm" else "confirm_request"
        details = {
            **(session.get("service_request_details") or {}),
            **self._extract_details(msg, session),
        }
        return "confirm_request" if not self._missing(details) else "ask_missing_details"

    def _metadata(self, next_action: str | None) -> Dict[str, Any]:
        trace = []
        if next_action:
            trace.append({"tool": next_action, "status": "selected"})
        return agent_metadata(self.config.agent_name, trace, next_action)


class TicketStatusWorkflow(BaseWorkflow):
    workflow_id = "ticket_status"
    title = "Ticket Status Lookup"
    active = True

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        session["workflow"] = self.workflow_id
        ticket_id = _extract_ticket_id(user_message)
        selected = choose_workflow_tool(
            agent_name="ticket_status_agent",
            system_prompt=(
                "You are a read-only ticket status workflow agent. Choose one "
                "allowlisted tool. Never create or mutate tickets."
            ),
            objective={"user_message": user_message, "ticket_id": ticket_id},
            tool_options={
                "ask_ticket_id": "Ask the user for a valid ticket id.",
                "lookup_ticket_status": "Look up an existing ticket by id.",
            },
        )
        next_action = selected["tool"] if selected else (
            "lookup_ticket_status" if ticket_id else "ask_ticket_id"
        )
        if not ticket_id:
            session["state"] = "awaiting_ticket_id"
            return AgentMessageResponse(
                message="Please provide the ticket id, for example INC1234ABCD.",
                workflow=self.workflow_id,
                state="awaiting_ticket_id",
                metadata=_metadata("ticket_status_agent", next_action),
            )

        ticket = mock_ticket_adapter.get(ticket_id.upper())
        session["state"] = "complete"
        if not ticket:
            return AgentMessageResponse(
                message=f"I could not find ticket {ticket_id.upper()} in the mock ticket system.",
                workflow=self.workflow_id,
                state="complete",
                metadata=_metadata("ticket_status_agent", next_action),
                requires_input=False,
            )
        return AgentMessageResponse(
            message=(
                f"Ticket {ticket['ticket_id']} is {ticket.get('status', 'Unknown')}. "
                f"Summary: {ticket.get('title', 'No title available')}."
            ),
            workflow=self.workflow_id,
            state="complete",
            cards=[UICard(kind="workflow", data={"title": self.title, "ticket": ticket})],
            metadata=_metadata("ticket_status_agent", next_action),
            requires_input=False,
        )


def password_reset_workflow() -> AgenticServiceRequestWorkflow:
    return AgenticServiceRequestWorkflow(
        ServiceWorkflowConfig(
            workflow_id="password_reset",
            title="Password Reset",
            agent_name="password_reset_agent",
            required_fields=["account"],
            field_labels={"account": "work email or account username"},
            initial_prompt="I can help start a password reset.",
            confirmation_prompt="I found enough information to submit a password reset request.",
            category="Identity Access",
            priority="Medium",
            extractor=_extract_account_details,
            validator=_validate_identity,
            completion=_complete_password_reset,
        )
    )


def account_unlock_workflow() -> AgenticServiceRequestWorkflow:
    return AgenticServiceRequestWorkflow(
        ServiceWorkflowConfig(
            workflow_id="account_unlock",
            title="Account Unlock",
            agent_name="account_unlock_agent",
            required_fields=["account"],
            field_labels={"account": "locked account email or username"},
            initial_prompt="I can help with an account unlock.",
            confirmation_prompt="I found enough information to submit an account unlock request.",
            category="Identity Access",
            priority="High",
            extractor=_extract_account_details,
            validator=_validate_identity,
            completion=_complete_account_unlock,
        )
    )


def vpn_access_workflow() -> AgenticServiceRequestWorkflow:
    return AgenticServiceRequestWorkflow(
        ServiceWorkflowConfig(
            workflow_id="vpn_access",
            title="VPN Access Request",
            agent_name="vpn_access_agent",
            required_fields=["requester", "business_reason", "duration"],
            field_labels={
                "requester": "requester email",
                "business_reason": "business reason",
                "duration": "access duration",
            },
            initial_prompt="I can help request VPN access.",
            confirmation_prompt="I have enough information to create a VPN access request.",
            category="Access Request",
            priority="Medium",
            extractor=_extract_vpn_details,
        )
    )


def software_install_workflow() -> AgenticServiceRequestWorkflow:
    return AgenticServiceRequestWorkflow(
        ServiceWorkflowConfig(
            workflow_id="software_install",
            title="Software Installation",
            agent_name="software_install_agent",
            required_fields=["software_name", "requester", "business_reason"],
            field_labels={
                "software_name": "software name",
                "requester": "requester email",
                "business_reason": "business reason",
            },
            initial_prompt="I can help request a software installation.",
            confirmation_prompt="I checked the mock software catalog and can submit this request.",
            category="Software Request",
            priority="Medium",
            extractor=_extract_software_details,
            validator=_validate_software,
        )
    )


def application_outage_workflow() -> AgenticServiceRequestWorkflow:
    return AgenticServiceRequestWorkflow(
        ServiceWorkflowConfig(
            workflow_id="application_outage",
            title="Application Outage",
            agent_name="application_outage_agent",
            required_fields=["app_name", "symptoms", "impact"],
            field_labels={
                "app_name": "application name",
                "symptoms": "symptoms/error",
                "impact": "affected users or business impact",
            },
            initial_prompt="I can help report an application outage.",
            confirmation_prompt="I have enough information to submit or update an outage report.",
            category="Application Outage",
            priority="High",
            extractor=_extract_outage_details,
            validator=_validate_outage,
            completion=_complete_outage,
        )
    )


def _extract_generic_details(msg: str, fields: Iterable[str]) -> Dict[str, str]:
    details: Dict[str, str] = {}
    email = _extract_email(msg)
    if email:
        for field_name in fields:
            if field_name in {"requester", "account"}:
                details[field_name] = email
    for field_name in fields:
        match = re.search(
            rf"(?:{field_name.replace('_', ' ')}|{field_name})\s*[:=-]\s*([^,;\n]+)",
            msg,
            flags=re.IGNORECASE,
        )
        if match:
            details[field_name] = match.group(1).strip()
    return details


def _extract_account_details(msg: str, session: Dict[str, Any]) -> Dict[str, str]:
    email = _extract_email(msg)
    if email:
        return {"account": email}
    match = re.search(r"\b(?:user|account|username)\s*[:=-]\s*([^,;\n]+)", msg, re.I)
    return {"account": match.group(1).strip()} if match else {}


def _extract_vpn_details(msg: str, session: Dict[str, Any]) -> Dict[str, str]:
    details = _extract_generic_details(msg, ["requester", "business_reason", "duration"])
    _fill_reason_and_duration(msg, details)
    return details


def _extract_software_details(msg: str, session: Dict[str, Any]) -> Dict[str, str]:
    details = _extract_generic_details(
        msg, ["software_name", "requester", "business_reason"]
    )
    for key in sorted(_SOFTWARE_CATALOG, key=len, reverse=True):
        if key in msg.lower():
            details["software_name"] = _SOFTWARE_CATALOG[key]["name"]
            break
    if "business_reason" not in details and len(msg.split()) > 5:
        details["business_reason"] = msg
    return details


def _extract_outage_details(msg: str, session: Dict[str, Any]) -> Dict[str, str]:
    details = _extract_generic_details(msg, ["app_name", "symptoms", "impact"])
    app_match = re.search(
        r"\b(?:app|application|service)\s*[:=-]\s*([^,;\n]+)", msg, re.I
    )
    if app_match:
        details["app_name"] = app_match.group(1).strip()
    elif len(msg.split()) >= 3:
        for token in ("salesforce", "servicenow", "jira", "slack", "teams", "outlook"):
            if token in msg.lower():
                details["app_name"] = token.title()
                break
    if "symptoms" not in details and any(
        word in msg.lower() for word in ("down", "error", "outage", "unavailable", "slow")
    ):
        details["symptoms"] = msg
    if "impact" not in details and any(
        word in msg.lower() for word in ("everyone", "team", "users", "department")
    ):
        details["impact"] = msg
    return details


def _validate_identity(details: Dict[str, Any]) -> Dict[str, Any]:
    account = str(details.get("account") or "").strip().lower()
    user = mock_identity_adapter.get_by_email(account) if "@" in account else None
    if user:
        return {"found": True, "user": user, "message": f"Found {user['full_name']} in mock identity."}
    return {
        "found": False,
        "message": "No matching mock identity user was found; a ticket will be created for manual handling.",
    }


def _validate_software(details: Dict[str, Any]) -> Dict[str, Any]:
    name = str(details.get("software_name") or "").lower()
    catalog_item = None
    for key, value in _SOFTWARE_CATALOG.items():
        if key in name or name in key:
            catalog_item = value
            break
    if not catalog_item:
        return {
            "catalog_match": False,
            "message": "Software was not found in the mock catalog; request will need review.",
        }
    return {
        "catalog_match": True,
        "software": catalog_item,
        "message": (
            f"{catalog_item['name']} is in the mock catalog. "
            + (
                "Approval is required."
                if catalog_item["approval_required"]
                else "No license approval is required."
            )
        ),
    }


def _validate_outage(details: Dict[str, Any]) -> Dict[str, Any]:
    app = _normalize_key(str(details.get("app_name") or ""))
    existing = _OUTAGE_REPORTS.get(app)
    if existing:
        return {
            "deduped": True,
            "existing": existing,
            "message": f"An outage report already exists for {details.get('app_name')}; I will update the impact.",
        }
    return {"deduped": False, "message": "No existing outage report found for this app."}


def _complete_outage(
    workflow_id: str, details: Dict[str, Any], validation: Dict[str, Any]
) -> Dict[str, Any]:
    if validation.get("deduped") and validation.get("existing"):
        ticket = validation["existing"]["ticket"]
        report = validation["existing"]
        report["updates"].append(details)
        message = f"Updated existing outage report {ticket['ticket_id']} for {details['app_name']}."
    else:
        completed = _create_service_ticket(
            ServiceWorkflowConfig(
                workflow_id=workflow_id,
                title="Application Outage",
                agent_name="application_outage_agent",
                required_fields=[],
                field_labels={},
                initial_prompt="",
                confirmation_prompt="",
                category="Application Outage",
                priority="High",
            ),
            details,
            validation,
        )
        ticket = completed["ticket"]
        report = {"ticket": ticket, "updates": [details]}
        _OUTAGE_REPORTS[_normalize_key(details["app_name"])] = report
        message = completed["message"]
    return {"ticket": ticket, "message": message}


def _complete_password_reset(
    workflow_id: str, details: Dict[str, Any], validation: Dict[str, Any]
) -> Dict[str, Any]:
    account = str(details.get("account") or "").strip().lower()
    if validation.get("found") and "@" in account:
        mock_identity_adapter.mark_password_reset_requested(account)
    completed = _create_service_ticket(
        ServiceWorkflowConfig(
            workflow_id=workflow_id,
            title="Password Reset",
            agent_name="password_reset_agent",
            required_fields=[],
            field_labels={},
            initial_prompt="",
            confirmation_prompt="",
            category="Identity Access",
            priority="Medium",
        ),
        details,
        validation,
    )
    if validation.get("found"):
        completed["message"] = (
            f"Password reset was recorded for {account}; ticket "
            f"{completed['ticket']['ticket_id']} was created for audit tracking."
        )
    return completed


def _complete_account_unlock(
    workflow_id: str, details: Dict[str, Any], validation: Dict[str, Any]
) -> Dict[str, Any]:
    account = str(details.get("account") or "").strip().lower()
    if validation.get("found") and "@" in account:
        mock_identity_adapter.unlock_account(account)
    completed = _create_service_ticket(
        ServiceWorkflowConfig(
            workflow_id=workflow_id,
            title="Account Unlock",
            agent_name="account_unlock_agent",
            required_fields=[],
            field_labels={},
            initial_prompt="",
            confirmation_prompt="",
            category="Identity Access",
            priority="High",
        ),
        details,
        validation,
    )
    if validation.get("found"):
        completed["message"] = (
            f"Account unlock was recorded for {account}; ticket "
            f"{completed['ticket']['ticket_id']} was created for audit tracking."
        )
    return completed


def _create_service_ticket(
    config: ServiceWorkflowConfig, details: Dict[str, Any], validation: Dict[str, Any]
) -> Dict[str, Any]:
    title = f"{config.title} - {_primary_detail(details)}"
    description = _format_details(details)
    if validation:
        description += "\n" + _format_details(validation)
    draft = TicketDraft(
        session_id=str(uuid.uuid4().hex),
        title=title[:120],
        description=description,
        category=config.category,
        priority=config.priority,
    )
    ticket = create_ticket(draft)
    return {
        "ticket": ticket,
        "message": f"{config.title} request submitted as ticket {ticket['ticket_id']}.",
    }


def _extract_email(text: str) -> Optional[str]:
    match = _EMAIL_RE.search(text or "")
    return match.group(0).lower() if match else None


def _extract_ticket_id(text: str) -> Optional[str]:
    match = _TICKET_RE.search(text or "")
    return match.group(0).upper() if match else None


def _fill_reason_and_duration(msg: str, details: Dict[str, str]) -> None:
    duration = re.search(r"\b(\d+\s*(?:day|days|week|weeks|month|months))\b", msg, re.I)
    if duration:
        details["duration"] = duration.group(1)
    if "business_reason" not in details and len(msg.split()) > 5:
        details["business_reason"] = msg


def _classify_confirmation(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    words = normalized.split()
    if any(token in words or token in normalized for token in _AFFIRMATIVE):
        return "confirm"
    if any(token in words or token in normalized for token in _NEGATIVE):
        return "cancel"
    return "unclear"


def _format_details(details: Dict[str, Any]) -> str:
    lines = []
    for key, value in details.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            value = ", ".join(f"{k}: {v}" for k, v in value.items())
        label = key.replace("_", " ").title()
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _primary_detail(details: Dict[str, Any]) -> str:
    for key in ("account", "software_name", "app_name", "requester"):
        if details.get(key):
            return str(details[key])
    return "request"


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _metadata(agent_name: str, next_action: str | None) -> Dict[str, Any]:
    trace = []
    if next_action:
        trace.append({"tool": next_action, "status": "selected"})
    return agent_metadata(agent_name, trace, next_action)
