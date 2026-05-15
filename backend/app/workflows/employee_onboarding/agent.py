"""Tool-using onboarding agent.

The workflow gathers and confirms user intent. Once confirmed, this module
lets a LangGraph ReAct agent decide and execute the approved onboarding tools.
If no LLM is configured, it falls back to the same tool sequence
deterministically so local demos still work.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.adapters.identity.mock_identity_adapter import mock_identity_adapter
from app.services.llm import llm_client


def run_onboarding_agent(employee: Dict[str, str], groups: List[str]) -> Dict[str, Any]:
    trace: list[dict] = []
    tools = _build_tools(trace)
    llm = llm_client()

    if llm is None:
        return _run_deterministic_tool_fallback(employee, groups, trace)

    agent = create_react_agent(
        llm,
        tools,
        messages_modifier=(
            "You are an enterprise IT onboarding agent. You may only use the provided "
            "tools. Never invent account changes. For a new employee, first call "
            "lookup_identity_user. If the user exists, stop and report duplicate. "
            "If absent, call create_ad_account, assign_role_based_access_groups, "
            "enroll_mfa, and send_welcome_email in a safe order. Return a concise "
            "summary of the performed tool calls."
        ),
    )
    objective = {
        "employee": employee,
        "groups": groups,
        "required_steps": [
            "lookup_identity_user",
            "create_ad_account only if lookup is absent",
            "assign_role_based_access_groups",
            "enroll_mfa",
            "send_welcome_email",
        ],
    }
    try:
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "Execute this approved onboarding request using tools:\n"
                            + json.dumps(objective, indent=2)
                        )
                    )
                ]
            }
        )
        final_message = result["messages"][-1].content if result.get("messages") else ""
        return _build_agent_result(employee, groups, trace, True, final_message)
    except Exception as exc:
        fallback = _run_deterministic_tool_fallback(employee, groups, trace)
        fallback["agent_error"] = str(exc)
        return fallback


def _build_tools(trace: list[dict]):
    @tool
    def lookup_identity_user(email: str) -> Dict[str, Any]:
        """Look up an employee by work email in the mock identity database."""
        user = mock_identity_adapter.get_by_email(email)
        event = {
            "tool": "lookup_identity_user",
            "status": "found" if user else "not_found",
            "email": email,
            "result": user,
        }
        trace.append(event)
        return event

    @tool
    def create_ad_account(
        full_name: str,
        email: str,
        department: str,
        role: str,
        manager: str | None = None,
    ) -> Dict[str, Any]:
        """Create a mock AD user account in the local identity database."""
        user = mock_identity_adapter.create_user(
            {
                "full_name": full_name,
                "email": email,
                "department": department,
                "role": role,
                "manager": manager,
            }
        )
        event = {"tool": "create_ad_account", "status": "complete", "result": user}
        trace.append(event)
        return event

    @tool
    def assign_role_based_access_groups(
        email: str, groups: List[str]
    ) -> Dict[str, Any]:
        """Assign approved role-based access groups to a mock identity user."""
        user = mock_identity_adapter.assign_groups(email, groups)
        event = {
            "tool": "assign_role_based_access_groups",
            "status": "complete",
            "groups": groups,
            "result": user,
        }
        trace.append(event)
        return event

    @tool
    def enroll_mfa(email: str) -> Dict[str, Any]:
        """Enroll MFA for a mock identity user."""
        user = mock_identity_adapter.enroll_mfa(email)
        event = {"tool": "enroll_mfa", "status": "complete", "result": user}
        trace.append(event)
        return event

    @tool
    def send_welcome_email(email: str) -> Dict[str, Any]:
        """Send a mock welcome email to a new employee."""
        user = mock_identity_adapter.mark_welcome_email_sent(email)
        event = {"tool": "send_welcome_email", "status": "complete", "result": user}
        trace.append(event)
        return event

    return [
        lookup_identity_user,
        create_ad_account,
        assign_role_based_access_groups,
        enroll_mfa,
        send_welcome_email,
    ]


def _run_deterministic_tool_fallback(
    employee: Dict[str, str], groups: List[str], trace: list[dict]
) -> Dict[str, Any]:
    existing = mock_identity_adapter.get_by_email(employee["email"])
    trace.append(
        {
            "tool": "lookup_identity_user",
            "status": "found" if existing else "not_found",
            "email": employee["email"],
            "result": existing,
        }
    )
    if existing:
        return _build_agent_result(
            employee,
            groups,
            trace,
            False,
            "Existing user found. Duplicate provisioning stopped.",
        )

    account = mock_identity_adapter.create_user(employee)
    trace.append({"tool": "create_ad_account", "status": "complete", "result": account})
    account = mock_identity_adapter.assign_groups(employee["email"], groups)
    trace.append(
        {
            "tool": "assign_role_based_access_groups",
            "status": "complete",
            "groups": groups,
            "result": account,
        }
    )
    account = mock_identity_adapter.enroll_mfa(employee["email"])
    trace.append({"tool": "enroll_mfa", "status": "complete", "result": account})
    account = mock_identity_adapter.mark_welcome_email_sent(employee["email"])
    trace.append(
        {"tool": "send_welcome_email", "status": "complete", "result": account}
    )
    return _build_agent_result(
        employee,
        groups,
        trace,
        False,
        "No LLM configured. Executed approved onboarding tools in deterministic order.",
    )


def _build_agent_result(
    employee: Dict[str, str],
    groups: List[str],
    trace: list[dict],
    used_llm_agent: bool,
    summary: str,
) -> Dict[str, Any]:
    duplicate = any(
        event["tool"] == "lookup_identity_user" and event["status"] == "found"
        for event in trace
    )
    latest_user = mock_identity_adapter.get_by_email(employee["email"])
    return {
        "agentic": used_llm_agent,
        "agent_summary": summary,
        "duplicate": duplicate,
        "employee": latest_user or employee,
        "account": latest_user,
        "groups": (latest_user or {}).get("groups", groups),
        "tool_trace": trace,
    }
