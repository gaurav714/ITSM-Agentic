"""New Employee Onboarding workflow."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from app.adapters.identity.mock_identity_adapter import mock_identity_adapter
from app.models.schemas import AgentMessageResponse, UICard
from app.services.llm import llm_structured
from app.workflows.employee_onboarding.agent import run_onboarding_agent
from app.workflows.base import BaseWorkflow

_AFFIRMATIVE = {
    "yes",
    "y",
    "confirm",
    "create",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "provision",
    "start",
    "do it",
}
_NEGATIVE = {"no", "n", "cancel", "stop", "abort", "not now", "never mind"}
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_NEW_ONBOARDING_RE = re.compile(
    r"\b(onboard|onboarding|new\s+(user|employee|hire)|joiner)\b",
    re.IGNORECASE,
)

_BASE_GROUPS = ["EMPLOYEE-BASELINE", "M365-STANDARD", "MFA-REQUIRED"]
_ROLE_GROUPS = {
    "developer": ["APP-DEV-USERS", "GIT-ACCESS", "VPN-ENGINEERING"],
    "engineer": ["APP-DEV-USERS", "GIT-ACCESS", "VPN-ENGINEERING"],
    "hr": ["HRIS-USERS", "EMPLOYEE-DATA-READERS"],
    "finance": ["FINANCE-APP-USERS", "EXPENSE-PORTAL-USERS"],
    "analyst": ["BI-USERS", "DATA-READERS"],
    "manager": ["PEOPLE-MANAGER-TOOLS", "APPROVAL-WORKFLOW-USERS"],
}

_DETAIL_EXTRACTION_PROMPT = """Extract new employee onboarding details from the user message.
Return null for fields the user did not provide.
Do not invent values. Plain department and role strings are enough.

User message:
{message}
"""

_CONFIRMATION_PROMPT = """The user was asked to confirm new employee provisioning.
Classify their reply as one of: confirm, cancel, unclear.
- confirm: user agrees to create/provision the account and onboarding steps
- cancel: user declines or asks to stop
- unclear: ambiguous or unrelated

User reply: {message}
"""


class _EmployeeDetails(BaseModel):
    full_name: Optional[str] = Field(None, description="Employee full name")
    email: Optional[str] = Field(None, description="Employee work email")
    department: Optional[str] = Field(None, description="Department/team")
    role: Optional[str] = Field(None, description="Role or job title")
    manager: Optional[str] = Field(None, description="Manager name, if provided")


class _Confirmation(BaseModel):
    decision: Literal["confirm", "cancel", "unclear"]


class NewEmployeeOnboardingWorkflow(BaseWorkflow):
    workflow_id = "new_employee_onboarding"
    title = "New Employee Onboarding"
    active = True

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        state = session.get("state", "idle")
        msg = (user_message or "").strip()

        if state in ("idle", None) or session.get("workflow") != self.workflow_id:
            self._start_new_request(session)
            if self._extract_details(msg):
                return self._handle_employee_details(session, msg)
            return AgentMessageResponse(
                message=(
                    "I can start a new employee onboarding request. "
                    "Please provide the employee's full name, work email, department, and role."
                ),
                workflow=self.workflow_id,
                state="awaiting_employee_details",
            )

        if state == "awaiting_employee_details":
            return self._handle_employee_details(session, msg)

        if state == "awaiting_confirmation":
            return self._handle_confirmation(session, msg.lower())

        if state == "complete":
            extracted = self._extract_details(msg)
            if extracted:
                self._start_new_request(session)
                return self._handle_employee_details(session, msg)
            if _NEW_ONBOARDING_RE.search(msg):
                self._start_new_request(session)
                return AgentMessageResponse(
                    message=(
                        "Let's start another onboarding request. Please provide the employee's "
                        "full name, work email, department, and role."
                    ),
                    workflow=self.workflow_id,
                    state="awaiting_employee_details",
                )
            return AgentMessageResponse(
                message=(
                    f"Onboarding request {session.get('onboarding_id')} is complete. "
                    "Send the next employee's full name, work email, department, and role to start another onboarding request."
                ),
                workflow=self.workflow_id,
                state="complete",
                requires_input=True,
            )

        return AgentMessageResponse(
            message="Please provide the employee's full name, work email, department, and role.",
            workflow=self.workflow_id,
            state="awaiting_employee_details",
        )

    def _start_new_request(self, session: Dict[str, Any]) -> None:
        session["workflow"] = self.workflow_id
        session["state"] = "awaiting_employee_details"
        for key in (
            "employee",
            "access_groups",
            "onboarding_id",
            "onboarding_result",
            "existing_identity_user",
        ):
            session.pop(key, None)

    def _handle_employee_details(
        self, session: Dict[str, Any], msg: str
    ) -> AgentMessageResponse:
        extracted = self._extract_details(msg)
        employee = {**(session.get("employee") or {}), **extracted}
        session["employee"] = employee

        missing = [
            label
            for key, label in (
                ("full_name", "full name"),
                ("email", "work email"),
                ("department", "department"),
                ("role", "role"),
            )
            if not employee.get(key)
        ]
        if missing:
            return AgentMessageResponse(
                message="I still need: " + ", ".join(missing) + ".",
                workflow=self.workflow_id,
                state="awaiting_employee_details",
            )

        groups = self._groups_for_role(employee["role"])
        session["access_groups"] = groups
        session["state"] = "awaiting_confirmation"

        return AgentMessageResponse(
            message=(
                "I interpreted the employee details and have enough information to onboard them. "
                "Reply 'yes' and the onboarding agent will check identity, create the account if needed, "
                "assign access groups, enroll MFA, and send the welcome email."
            ),
            workflow=self.workflow_id,
            state="awaiting_confirmation",
            cards=[
                UICard(
                    kind="onboarding_progress",
                    data={
                        "employee": employee,
                        "groups": groups,
                        "steps": self._steps(groups, "pending", employee),
                    },
                )
            ],
        )

    def _handle_confirmation(
        self, session: Dict[str, Any], lower: str
    ) -> AgentMessageResponse:
        decision = self._classify_confirmation(lower)
        if decision == "cancel":
            session["state"] = "idle"
            return AgentMessageResponse(
                message="Onboarding cancelled. No account or access changes were made.",
                workflow=self.workflow_id,
                state="idle",
                requires_input=False,
            )
        if decision == "unclear":
            return AgentMessageResponse(
                message="Please reply 'yes' to provision onboarding or 'no' to cancel.",
                workflow=self.workflow_id,
                state="awaiting_confirmation",
            )

        employee = session["employee"]
        groups = session["access_groups"]
        agent_result = run_onboarding_agent(employee, groups)
        account = agent_result["account"]
        duplicate = agent_result["duplicate"]
        steps = self._steps_from_tool_trace(agent_result["tool_trace"], employee, groups)

        if duplicate:
            session["state"] = "idle"
            session["existing_identity_user"] = account
            return AgentMessageResponse(
                message=(
                    f"{employee['email']} already exists in the mock identity database. "
                    "The onboarding agent stopped without creating a duplicate account."
                ),
                workflow=self.workflow_id,
                state="idle",
                cards=[
                    UICard(
                        kind="onboarding_progress",
                        data={
                            **agent_result,
                            "steps": steps,
                        },
                    )
                ],
                requires_input=False,
            )

        result = {
            "onboarding_id": f"ONB-{uuid.uuid4().hex[:8].upper()}",
            "employee": employee,
            "groups": groups,
            "account": account,
            "steps": steps,
            "agentic": agent_result["agentic"],
            "agent_summary": agent_result["agent_summary"],
            "tool_trace": agent_result["tool_trace"],
        }
        session["onboarding_id"] = result["onboarding_id"]
        session["onboarding_result"] = result
        session["state"] = "complete"

        return AgentMessageResponse(
            message=(
                f"Onboarding request {result['onboarding_id']} completed for "
                f"{employee['full_name']}. The onboarding agent checked identity, stored mock AD account "
                f"{account['username']} in the local database, assigned access groups, enrolled MFA, "
                "and sent the welcome email."
            ),
            workflow=self.workflow_id,
            state="complete",
            cards=[UICard(kind="onboarding_progress", data=result)],
            requires_input=False,
        )

    @staticmethod
    def _extract_details(msg: str) -> Dict[str, str]:
        llm_details = llm_structured(
            _DETAIL_EXTRACTION_PROMPT.format(message=msg),
            _EmployeeDetails,
        )
        if llm_details is not None:
            cleaned = {
                key: value.strip()
                for key, value in llm_details.model_dump().items()
                if isinstance(value, str) and value.strip()
            }
            if cleaned.get("email") and not _EMAIL_RE.fullmatch(cleaned["email"]):
                cleaned.pop("email")
            if cleaned:
                return cleaned

        details: Dict[str, str] = {}
        email = _EMAIL_RE.search(msg)
        if email:
            details["email"] = email.group(0).lower()

        label_patterns = {
            "full_name": r"(?:full\s+name|name|employee)\s*[:=-]\s*([^,;\n]+)",
            "department": r"(?:department|dept|team)\s*[:=-]\s*([^,;\n]+)",
            "role": r"(?:role|job\s+title|title)\s*[:=-]\s*([^,;\n]+)",
            "manager": r"(?:manager)\s*[:=-]\s*([^,;\n]+)",
        }
        for key, pattern in label_patterns.items():
            match = re.search(pattern, msg, flags=re.IGNORECASE)
            if match:
                details[key] = match.group(1).strip()

        parts = [p.strip() for p in re.split(r"[,;\n]+", msg) if p.strip()]
        if len(parts) >= 4 and "full_name" not in details:
            details["full_name"] = parts[0]
        if len(parts) >= 4 and "department" not in details:
            details["department"] = parts[2]
        if len(parts) >= 4 and "role" not in details:
            details["role"] = parts[3]

        if details.get("email") and "full_name" not in details:
            local = details["email"].split("@", 1)[0]
            candidate = " ".join(piece.capitalize() for piece in re.split(r"[._-]+", local))
            if len(candidate.split()) >= 2:
                details["full_name"] = candidate

        return {key: value.strip() for key, value in details.items() if value.strip()}

    @staticmethod
    def _groups_for_role(role: str) -> list[str]:
        groups = list(_BASE_GROUPS)
        role_text = role.lower()
        for token, mapped_groups in _ROLE_GROUPS.items():
            if token in role_text:
                groups.extend(mapped_groups)
        return list(dict.fromkeys(groups))

    @staticmethod
    def _steps(groups: list[str], status: str, employee: Dict[str, str]) -> list[dict]:
        email = employee.get("email", "employee")
        username = email.split("@", 1)[0]
        details = {
            "pending": [
                "Create user object with a generated temporary password.",
                ", ".join(groups),
                "Send MFA registration invitation and mark MFA as required.",
                "Send welcome message with first-day instructions.",
            ],
            "complete": [
                f"Created mock AD account {username}.",
                ", ".join(groups),
                f"MFA enrollment invite sent to {email}.",
                f"Welcome email sent to {email}.",
            ],
        }
        labels = [
            "Create AD account",
            "Assign Role based Access Groups",
            "Enroll MFA",
            "Send welcome Email",
        ]
        return [
            {"label": label, "status": status, "detail": detail}
            for label, detail in zip(labels, details[status])
        ]

    @staticmethod
    def _existing_user_steps(user: Dict[str, Any]) -> list[dict]:
        return [
            {
                "label": "Check existing account",
                "status": "complete",
                "detail": f"Found {user['username']} in {user['directory']}.",
            },
            {
                "label": "Create AD account",
                "status": "skipped",
                "detail": "Skipped to prevent a duplicate account.",
            },
            {
                "label": "Assign Role based Access Groups",
                "status": "skipped",
                "detail": "Existing groups: " + ", ".join(user["groups"]),
            },
            {
                "label": "Enroll MFA",
                "status": "skipped",
                "detail": "No MFA change was made for the existing account.",
            },
            {
                "label": "Send welcome Email",
                "status": "skipped",
                "detail": "No welcome email was sent for the duplicate request.",
            },
        ]

    @staticmethod
    def _steps_from_tool_trace(
        trace: list[dict], employee: Dict[str, str], groups: list[str]
    ) -> list[dict]:
        tool_status = {event["tool"]: event["status"] for event in trace}
        lookup_found = tool_status.get("lookup_identity_user") == "found"
        email = employee["email"]
        username = email.split("@", 1)[0]
        if lookup_found:
            return [
                {
                    "label": "Check existing account",
                    "status": "complete",
                    "detail": f"The agent found an existing account for {email}.",
                },
                {
                    "label": "Create AD account",
                    "status": "skipped",
                    "detail": "Skipped to prevent a duplicate account.",
                },
                {
                    "label": "Assign Role based Access Groups",
                    "status": "skipped",
                    "detail": "No group changes were made for the duplicate request.",
                },
                {
                    "label": "Enroll MFA",
                    "status": "skipped",
                    "detail": "No MFA changes were made for the duplicate request.",
                },
                {
                    "label": "Send welcome Email",
                    "status": "skipped",
                    "detail": "No welcome email was sent for the duplicate request.",
                },
            ]

        labels = [
            (
                "lookup_identity_user",
                "Check existing account",
                f"The agent found no existing account for {email}.",
            ),
            (
                "create_ad_account",
                "Create AD account",
                f"Created mock AD account {username}.",
            ),
            (
                "assign_role_based_access_groups",
                "Assign Role based Access Groups",
                ", ".join(groups),
            ),
            (
                "enroll_mfa",
                "Enroll MFA",
                f"MFA enrollment invite sent to {email}.",
            ),
            (
                "send_welcome_email",
                "Send welcome Email",
                f"Welcome email sent to {email}.",
            ),
        ]
        return [
            {
                "label": label,
                "status": "complete" if tool_name in tool_status else "pending",
                "detail": detail,
            }
            for tool_name, label, detail in labels
        ]

    @staticmethod
    def _classify_confirmation(lower: str) -> Literal["confirm", "cancel", "unclear"]:
        normalized = re.sub(r"[^a-z0-9\s]", " ", lower)
        words = normalized.split()
        if any(tok == lower or tok in words or tok in normalized for tok in _AFFIRMATIVE):
            return "confirm"
        if any(tok == lower or tok in words or tok in normalized for tok in _NEGATIVE):
            return "cancel"
        result = llm_structured(
            _CONFIRMATION_PROMPT.format(message=lower),
            _Confirmation,
        )
        if result is not None:
            return result.decision
        return "unclear"
