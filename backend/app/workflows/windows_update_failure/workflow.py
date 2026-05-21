"""Agent-owned Windows Update Failure workflow.

The LLM agent interprets the raw user message and chooses the next workflow
action. Deterministic code only enforces safety gates and optional demo fallback.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from app.config import get_settings
from app.models.schemas import AgentMessageResponse, UICard
from app.workflows.base import BaseWorkflow
from app.workflows.windows_update_failure.agent import run_windows_update_decision_agent

_WINDOWS_UPDATE_TOOL_ALLOWLIST = {
    "collect_windows_update_status": {
        "label": "Collect Windows Update status",
        "scope": "Read Windows Update service status and pending reboot state",
    },
    "open_windows_update_settings": {
        "label": "Open Windows Update settings",
        "scope": "Open Windows Update settings only",
    },
}
_CHECKS = {
    "vpn_connected": {
        "label": "VPN connected if required",
        "prompt": "Please confirm whether you are connected to VPN if your company requires VPN for Windows updates.",
    },
    "internet_ok": {
        "label": "Internet connection stable",
        "prompt": "Please check whether your internet connection is stable, then try Windows Update again.",
    },
    "restarted": {
        "label": "Device restarted",
        "prompt": "Please restart the device, then try Windows Update again.",
    },
    "disk_space_checked": {
        "label": "Disk space checked",
        "prompt": "Please check that there is enough free disk space for the update.",
    },
}
_CHECK_ORDER = ["vpn_connected", "internet_ok", "restarted", "disk_space_checked"]


class WindowsUpdateState(TypedDict, total=False):
    session_state: str
    user_message: str
    conversation_summary: str
    checks_discussed: list[str]
    current_check: str
    access_approved: bool
    tool_results: list[dict]
    local_action_received: bool
    pending_tool: str
    next_decision: Literal[
        "ask_check",
        "request_access",
        "run_tool",
        "resolved",
        "deny_or_cancel",
        "clarify",
        "agent_error",
    ]
    selected_check: str
    selected_tool: str
    assistant_message: str
    rationale: str
    agentic: bool
    llm_called: bool
    agent_trace: list[dict]
    agent_summary: str
    agent_error: str
    response: AgentMessageResponse


class _AgentDecision(BaseModel):
    decision: Literal[
        "ask_check",
        "request_access",
        "run_tool",
        "resolved",
        "deny_or_cancel",
        "clarify",
        "agent_error",
    ]
    selected_check: str = ""
    selected_tool: str = ""
    message: str = ""
    rationale: str = ""


class WindowsUpdateFailureWorkflow(BaseWorkflow):
    workflow_id = "windows_update_failure"
    title = "Windows Update Failure"
    active = True

    def __init__(self) -> None:
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(WindowsUpdateState)
        graph.add_node("agent_interpret_and_decide", self._agent_interpret_and_decide)
        graph.add_node("prompt_user_check", self._prompt_user_check)
        graph.add_node("request_local_access", self._request_local_access)
        graph.add_node("trigger_local_tool", self._trigger_local_tool)
        graph.add_node("finish_or_clarify", self._finish_or_clarify)

        graph.set_entry_point("agent_interpret_and_decide")
        graph.add_conditional_edges(
            "agent_interpret_and_decide",
            self._route_decision,
            {
                "prompt_user_check": "prompt_user_check",
                "request_local_access": "request_local_access",
                "trigger_local_tool": "trigger_local_tool",
                "finish_or_clarify": "finish_or_clarify",
            },
        )
        graph.add_edge("prompt_user_check", END)
        graph.add_edge("request_local_access", END)
        graph.add_edge("trigger_local_tool", END)
        graph.add_edge("finish_or_clarify", END)
        return graph.compile()

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        if session.get("workflow") != self.workflow_id:
            self._start_session(session)

        if session.get("state") == "complete":
            self._start_session(session)

        local_action_result = session.pop("local_action_result", None)
        if local_action_result:
            session.setdefault("windows_update_tool_results", []).append(
                local_action_result
            )
            session["windows_update_pending_tool"] = ""

        graph_state = self._graph.invoke(
            {
                "session_state": session.get("state", "idle"),
                "user_message": user_message or "",
                "conversation_summary": _conversation_summary(session),
                "checks_discussed": session.get("windows_update_checks_discussed")
                or [],
                "current_check": session.get("windows_update_current_check") or "",
                "access_approved": bool(
                    session.get("windows_update_access_approved")
                ),
                "tool_results": session.get("windows_update_tool_results") or [],
                "local_action_received": bool(local_action_result),
                "pending_tool": session.get("windows_update_pending_tool") or "",
            }
        )

        if graph_state.get("next_decision") == "ask_check":
            check_id = graph_state.get("selected_check", "")
            session["windows_update_current_check"] = check_id
            session["windows_update_checks_discussed"] = _merge_checks(
                session.get("windows_update_checks_discussed") or [],
                [check_id],
            )
        else:
            session["windows_update_current_check"] = ""

        session["windows_update_last_decision"] = {
            "decision": graph_state.get("next_decision"),
            "selected_check": graph_state.get("selected_check", ""),
            "selected_tool": graph_state.get("selected_tool", ""),
            "message": graph_state.get("assistant_message", ""),
            "rationale": graph_state.get("rationale", ""),
            "agentic": bool(graph_state.get("agentic")),
            "llm_called": bool(graph_state.get("llm_called")),
            "agent_summary": graph_state.get("agent_summary", ""),
            "agent_error": graph_state.get("agent_error", ""),
        }
        session["windows_update_llm_called"] = bool(graph_state.get("llm_called"))
        session["windows_update_agent_error"] = graph_state.get("agent_error", "")
        trace = session.setdefault("windows_update_agent_trace", [])
        agent_trace = graph_state.get("agent_trace") or []
        if agent_trace:
            trace.extend(agent_trace)
        else:
            trace.append(session["windows_update_last_decision"])
        session["windows_update_access_approved"] = bool(
            graph_state.get("access_approved")
        )

        response = graph_state["response"]
        session["state"] = response.state
        if graph_state.get("next_decision") == "run_tool":
            session["windows_update_pending_tool"] = graph_state.get(
                "selected_tool", ""
            )
        elif response.state != "awaiting_tool_result":
            session["windows_update_pending_tool"] = ""
        return response

    def _start_session(self, session: Dict[str, Any]) -> None:
        session["workflow"] = self.workflow_id
        session["state"] = "idle"
        session["windows_update_checks_discussed"] = []
        session["windows_update_agent_trace"] = []
        session["windows_update_last_decision"] = None
        session["windows_update_access_approved"] = False
        session["windows_update_tool_results"] = []
        session["windows_update_current_check"] = ""
        session["windows_update_pending_tool"] = ""
        session.pop("local_action_result", None)

    def _agent_interpret_and_decide(
        self, state: WindowsUpdateState
    ) -> WindowsUpdateState:
        decision_result = _decide_next_step(state)
        decision = decision_result["decision"]
        access_approved = bool(state.get("access_approved"))
        if decision.decision == "run_tool":
            access_approved = True
        if decision.decision == "request_access":
            access_approved = False
        return {
            **state,
            "next_decision": decision.decision,
            "selected_check": decision.selected_check,
            "selected_tool": decision.selected_tool,
            "assistant_message": decision.message,
            "rationale": decision.rationale,
            "agentic": decision_result["agentic"],
            "llm_called": decision_result.get("llm_called", False),
            "agent_trace": decision_result["trace"],
            "agent_summary": decision_result.get("summary", ""),
            "agent_error": decision_result.get("agent_error", ""),
            "access_approved": access_approved,
        }

    @staticmethod
    def _route_decision(state: WindowsUpdateState) -> str:
        decision = state.get("next_decision")
        if decision == "ask_check":
            return "prompt_user_check"
        if decision == "request_access":
            return "request_local_access"
        if decision == "run_tool":
            return "trigger_local_tool"
        return "finish_or_clarify"

    def _prompt_user_check(self, state: WindowsUpdateState) -> WindowsUpdateState:
        selected_check = _valid_or_next_check(
            state.get("selected_check"),
            state.get("checks_discussed") or [],
        )
        check = _CHECKS[selected_check]
        message = state.get("assistant_message") or check["prompt"]
        response = AgentMessageResponse(
            message=message,
            workflow=self.workflow_id,
            state="awaiting_agent_followup",
            cards=[self._decision_card(state, "agent_selected_check")],
        )
        return {**state, "selected_check": selected_check, "response": response}

    def _request_local_access(self, state: WindowsUpdateState) -> WindowsUpdateState:
        response = AgentMessageResponse(
            message=(
                state.get("assistant_message")
                or "Allow the agent to run allowlisted Windows Update tools on this device?"
            ),
            workflow=self.workflow_id,
            state="awaiting_access_approval",
            cards=[self._decision_card(state, "agent_requested_access")],
        )
        return {**state, "response": response}

    def _trigger_local_tool(self, state: WindowsUpdateState) -> WindowsUpdateState:
        selected_tool = state.get("selected_tool") or "open_windows_update_settings"
        if selected_tool not in _WINDOWS_UPDATE_TOOL_ALLOWLIST:
            return _agent_error_state(
                state,
                f"Agent selected a non-allowlisted tool: {selected_tool}",
            )
        tool = _WINDOWS_UPDATE_TOOL_ALLOWLIST[selected_tool]
        response = AgentMessageResponse(
            message=f"I'll ask the local app server to {tool['label'].lower()} now.",
            workflow=self.workflow_id,
            state="awaiting_tool_result",
            metadata={
                "trigger_local_app_action": {
                    "action": selected_tool,
                    "device_name": "LOCAL-ENDPOINT",
                }
            },
            cards=[self._decision_card(state, "agent_selected_tool")],
            requires_input=False,
        )
        return {**state, "selected_tool": selected_tool, "response": response}

    def _finish_or_clarify(self, state: WindowsUpdateState) -> WindowsUpdateState:
        decision = state.get("next_decision")
        if decision == "agent_error":
            return _agent_error_state(
                state, state.get("agent_error") or "Unknown LLM decision error."
            )

        if decision == "resolved":
            response = AgentMessageResponse(
                message=(
                    state.get("assistant_message")
                    or "Great, Windows Update is working now. I'll close this workflow."
                ),
                workflow=self.workflow_id,
                state="complete",
                requires_input=False,
                cards=[self._decision_card(state, "agent_marked_resolved")],
            )
            return {**state, "response": response}

        if decision == "deny_or_cancel":
            response = AgentMessageResponse(
                message=(
                    state.get("assistant_message")
                    or "No problem. I will not access the device. You can restart this workflow if you want to try again later."
                ),
                workflow=self.workflow_id,
                state="complete",
                requires_input=False,
                cards=[self._decision_card(state, "agent_stopped_workflow")],
            )
            return {**state, "response": response}

        response = AgentMessageResponse(
            message=(
                state.get("assistant_message")
                or "Could you clarify whether Windows Update is working now or still failing?"
            ),
            workflow=self.workflow_id,
            state="awaiting_agent_followup",
            cards=[self._decision_card(state, "agent_clarified")],
        )
        return {**state, "response": response}

    def _decision_card(self, state: WindowsUpdateState, step: str) -> UICard:
        return UICard(
            kind="workflow",
            data={
                "title": self.title,
                "step": step,
                "decision": state.get("next_decision"),
                "selected_check": state.get("selected_check", ""),
                "selected_tool": state.get("selected_tool", ""),
                "message": state.get("assistant_message", ""),
                "rationale": state.get("rationale", ""),
                "checks_discussed": state.get("checks_discussed") or [],
                "current_check": state.get("current_check", ""),
                "access_approved": bool(state.get("access_approved")),
                "pending_tool": state.get("pending_tool", ""),
                "available_tools": list(_WINDOWS_UPDATE_TOOL_ALLOWLIST),
                "agentic": bool(state.get("agentic")),
                "llm_called": bool(state.get("llm_called")),
                "agent_trace": state.get("agent_trace") or [],
                "agent_error": state.get("agent_error", ""),
            },
        )


def _decide_next_step(state: WindowsUpdateState) -> Dict[str, Any]:
    checks_discussed = state.get("checks_discussed") or []
    session_state = state.get("session_state") or "idle"
    protocol_decision = _protocol_decision(state)
    if protocol_decision:
        return {
            "decision": protocol_decision,
            "agentic": False,
            "llm_called": False,
            "trace": [
                {
                    "decision": protocol_decision.decision,
                    "selected_check": protocol_decision.selected_check,
                    "selected_tool": protocol_decision.selected_tool,
                    "message": protocol_decision.message,
                    "rationale": protocol_decision.rationale,
                    "source": "deterministic_protocol_gate",
                }
            ],
            "summary": "",
            "agent_error": "",
        }

    context = {
        "session_state": session_state,
        "latest_user_message": state.get("user_message") or "",
        "conversation_summary": state.get("conversation_summary") or "",
        "checks_discussed": checks_discussed,
        "missing_checks": _missing_checks(checks_discussed),
        "current_prompted_check": state.get("current_check") or "",
        "access_approved": bool(state.get("access_approved")),
        "awaiting_local_access_approval": session_state == "awaiting_access_approval",
        "access_request_already_sent": session_state == "awaiting_access_approval",
        "recommended_first_tool": "collect_windows_update_status",
        "checks_discussed_count": len(checks_discussed),
        "previous_local_tool_results": state.get("tool_results") or [],
        "available_checks": {
            check_id: check["label"] for check_id, check in _CHECKS.items()
        },
        "allowlisted_tools": list(_WINDOWS_UPDATE_TOOL_ALLOWLIST.keys()),
    }
    agent_result = run_windows_update_decision_agent(context)
    if agent_result and agent_result.get("decision"):
        decision = _AgentDecision.model_validate(agent_result["decision"])
        return {
            "decision": _sanitize_decision(decision, state),
            "agentic": bool(agent_result.get("agentic")),
            "llm_called": bool(agent_result.get("llm_called")),
            "trace": agent_result.get("trace") or [],
            "summary": agent_result.get("summary", ""),
            "agent_error": agent_result.get("agent_error", ""),
        }

    if get_settings().windows_update_allow_deterministic_fallback:
        fallback = _fallback_decision(state)
        return {
            "decision": fallback,
            "agentic": False,
            "llm_called": bool((agent_result or {}).get("llm_called")),
            "trace": [
                {
                    "decision": fallback.decision,
                    "selected_check": fallback.selected_check,
                    "selected_tool": fallback.selected_tool,
                    "message": fallback.message,
                    "rationale": fallback.rationale,
                    "source": "deterministic_fallback",
                    "agent_error": (agent_result or {}).get("agent_error", ""),
                }
            ],
            "summary": "",
            "agent_error": (agent_result or {}).get("agent_error", "")
            if agent_result
            else "",
        }

    error = (agent_result or {}).get("agent_error", "") or "llm_decision_unavailable"
    return {
        "decision": _AgentDecision(
            decision="agent_error",
            message="",
            rationale="The workflow requires an LLM decision and fallback is disabled.",
        ),
        "agentic": False,
        "llm_called": bool((agent_result or {}).get("llm_called")),
        "trace": agent_result.get("trace") if agent_result else [],
        "summary": (agent_result or {}).get("summary", ""),
        "agent_error": error,
    }


def _protocol_decision(state: WindowsUpdateState) -> _AgentDecision | None:
    session_state = state.get("session_state") or "idle"
    message = state.get("user_message") or ""
    latest_tool = _latest_tool_result(state.get("tool_results") or [])

    if state.get("local_action_received"):
        return _AgentDecision(
            decision="clarify",
            message=_local_tool_result_message(latest_tool),
            rationale="Summarized the local app action result received from the browser.",
        )

    if session_state == "awaiting_tool_result":
        pending_tool = state.get("pending_tool") or "the requested local tool"
        return _AgentDecision(
            decision="clarify",
            message=(
                f"I already sent the {pending_tool} request to the local app. "
                "I am waiting for the browser to return the result. If nothing happens, "
                "make sure the local diagnostic app is running at http://127.0.0.1:8765."
            ),
            rationale="Prevented re-triggering the same pending local app action.",
        )

    if session_state != "awaiting_access_approval":
        return None

    if _is_clear_approval(message):
        return _AgentDecision(
            decision="run_tool",
            selected_tool="collect_windows_update_status",
            rationale="User explicitly approved local Windows Update diagnostics.",
        )

    if _is_clear_denial(message):
        return _AgentDecision(
            decision="deny_or_cancel",
            message=(
                "No problem. I will not access this device. You can restart the "
                "Windows Update workflow later if you want to run local diagnostics."
            ),
            rationale="User denied or cancelled local workstation access.",
        )

    return _AgentDecision(
        decision="clarify",
        message=(
            "Please reply yes to approve the local Windows Update diagnostic check, "
            "or no to stop."
        ),
        rationale="Access approval reply was ambiguous.",
    )


def _sanitize_decision(
    decision: _AgentDecision, state: WindowsUpdateState
) -> _AgentDecision:
    selected_check = decision.selected_check
    selected_tool = decision.selected_tool
    session_state = state.get("session_state")
    checks_discussed = state.get("checks_discussed") or []

    if (
        decision.decision == "run_tool"
        and not state.get("access_approved")
        and session_state != "awaiting_access_approval"
    ):
        return _AgentDecision(
            decision="request_access",
            message=(
                "I can check the workstation with allowlisted Windows Update tools. "
                "Do I have your permission to run those local checks?"
            ),
            rationale="Local tools require explicit access approval first.",
        )
    if decision.decision == "request_access" and session_state == "awaiting_access_approval":
        return _AgentDecision(
            decision="clarify",
            message=(
                "I already asked for local workstation access. Please reply yes "
                "to approve running the local Windows Update check, or no to stop."
            ),
            rationale=(
                "Prevented repeated access request while waiting for the user's "
                "approval answer."
            ),
        )
    if decision.decision == "run_tool" and selected_tool not in _WINDOWS_UPDATE_TOOL_ALLOWLIST:
        return _AgentDecision(
            decision="agent_error",
            message="",
            rationale=f"Agent selected non-allowlisted tool: {selected_tool}",
        )
    if decision.decision == "ask_check" and (
        selected_check not in _CHECKS or selected_check in checks_discussed
    ):
        selected_check = _next_missing_check(checks_discussed)
        if not selected_check:
            return _AgentDecision(
                decision="request_access",
                message=(
                    "We have covered the basic checks. Do I have your permission "
                    "to run an allowlisted local Windows Update check on this device?"
                ),
                rationale=(
                    "Agent selected a duplicate or unknown check and no known "
                    "check remains, so the next safe step is local access."
                ),
            )

    return _AgentDecision(
        decision=decision.decision,
        selected_check=selected_check,
        selected_tool=selected_tool,
        message=decision.message,
        rationale=decision.rationale,
    )


def _agent_error_state(state: WindowsUpdateState, error: str) -> WindowsUpdateState:
    response = AgentMessageResponse(
        message=(
            "I cannot continue the Windows Update agentic workflow because "
            "the LLM decision step failed. Please check OPENAI_API_KEY and "
            "OPENAI_MODEL, then restart this workflow."
        ),
        workflow=WindowsUpdateFailureWorkflow.workflow_id,
        state="awaiting_agent_error",
        cards=[
            UICard(
                kind="workflow",
                data={
                    "title": WindowsUpdateFailureWorkflow.title,
                    "step": "agent_decision_error",
                    "agentic": False,
                    "llm_called": bool(state.get("llm_called")),
                    "agent_error": error,
                    "agent_trace": state.get("agent_trace") or [],
                },
            )
        ],
        requires_input=False,
        metadata={
            "agentic": False,
            "llm_called": bool(state.get("llm_called")),
            "agent_error": error,
        },
    )
    return {**state, "next_decision": "agent_error", "agent_error": error, "response": response}


def _fallback_decision(state: WindowsUpdateState) -> _AgentDecision:
    checks_discussed = state.get("checks_discussed") or []
    access_approved = bool(state.get("access_approved"))
    latest_tool = _latest_tool_result(state.get("tool_results") or [])
    if state.get("session_state") == "awaiting_access_approval":
        return _AgentDecision(
            decision="run_tool",
            selected_tool="collect_windows_update_status",
            message="",
            rationale="Demo fallback assumes access was approved.",
        )
    if state.get("session_state") == "awaiting_tool_result":
        return _AgentDecision(
            decision="clarify",
            message=_local_tool_result_message(latest_tool)
            if latest_tool
            else "I am waiting for the local Windows Update diagnostic result.",
            rationale="Demo fallback does not re-run a pending local action.",
        )
    if len(checks_discussed) < 2:
        check_id = _next_missing_check(checks_discussed)
        return _AgentDecision(
            decision="ask_check",
            selected_check=check_id,
            message=_CHECKS[check_id]["prompt"],
            rationale="Demo fallback asks basic checks before access.",
        )
    if access_approved:
        return _AgentDecision(
            decision="run_tool",
            selected_tool=_fallback_tool_for_state(state),
            message="",
            rationale="Demo fallback runs the next allowlisted tool.",
        )
    return _AgentDecision(
        decision="request_access",
        message="Do I have permission to run allowlisted Windows Update checks on this device?",
        rationale="Demo fallback requests access after basic checks.",
    )


def _conversation_summary(session: Dict[str, Any]) -> str:
    messages = session.get("messages") or []
    recent = messages[-8:]
    return "\n".join(
        f"{item.get('role', 'unknown')}: {item.get('content', '')}"
        for item in recent
        if isinstance(item, dict)
    )


def _missing_checks(checks_discussed: list[str]) -> list[str]:
    return [check for check in _CHECK_ORDER if check not in checks_discussed]


def _next_missing_check(checks_discussed: list[str]) -> str:
    missing = _missing_checks(checks_discussed)
    return missing[0] if missing else ""


def _valid_or_next_check(
    selected_check: str | None, checks_discussed: list[str]
) -> str:
    if selected_check in _CHECKS:
        return selected_check
    return _next_missing_check(checks_discussed) or _CHECK_ORDER[-1]


def _latest_tool_result(results: list[dict]) -> dict:
    for result in reversed(results):
        if isinstance(result, dict):
            return result
    return {}


def _fallback_tool_for_state(state: WindowsUpdateState) -> str:
    tool_results = state.get("tool_results") or []
    used_tools = {
        result.get("action") for result in tool_results if isinstance(result, dict)
    }
    if "collect_windows_update_status" not in used_tools:
        return "collect_windows_update_status"
    return "open_windows_update_settings"


def _is_clear_approval(message: str) -> bool:
    text = f" {(message or '').lower()} "
    return bool(
        re.search(
            r"\b(yes|yep|yeah|ok|okay|approved?|allow|grant|go ahead|proceed|"
            r"run it|do it|you have permission|i have the permission|access my device)\b",
            text,
        )
    ) and not _is_clear_denial(message)


def _is_clear_denial(message: str) -> bool:
    text = f" {(message or '').lower()} "
    return bool(
        re.search(
            r"\b(no|nope|deny|denied|do not|don't|dont|stop|cancel|never mind|"
            r"not now)\b",
            text,
        )
    )


def _local_tool_result_message(result: dict) -> str:
    if not result:
        return (
            "I did not receive a local Windows Update diagnostic result yet. "
            "Please make sure the local diagnostic app is running at "
            "http://127.0.0.1:8765, then try again."
        )

    action = result.get("action") or "local app action"
    status = result.get("status") or "unknown"
    message = result.get("message") or "The local app returned a result."
    errors = result.get("errors") or []

    if status == "failed" or errors and "local_app_unreachable" in errors:
        return (
            "I could not reach the local diagnostic app, so the Windows Update "
            "check did not run. Start the local app server on this workstation "
            "at http://127.0.0.1:8765, then ask me to retry the local check."
        )

    if action == "collect_windows_update_status":
        lines = [f"{message} Status: {status}."]
        services = result.get("service_statuses") or {}
        if services:
            service_bits = []
            for name, data in services.items():
                if isinstance(data, dict):
                    service_bits.append(f"{name}={data.get('status', 'unknown')}")
            if service_bits:
                lines.append("Services: " + ", ".join(service_bits) + ".")
        pending_reboot = result.get("pending_reboot")
        if pending_reboot is not None:
            lines.append(
                "Pending reboot: " + ("yes." if pending_reboot else "no.")
            )
        if errors:
            lines.append("Warnings: " + "; ".join(str(error) for error in errors) + ".")
        lines.append(
            "Please try Windows Update again. If it is still failing, tell me and "
            "I can open Windows Update settings next."
        )
        return " ".join(lines)

    if action == "open_windows_update_settings":
        return (
            f"{message} Status: {status}. Please try Windows Update again. "
            "Is it working now, or is the issue still happening?"
        )

    return f"{message} Status: {status}."


def _merge_checks(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for check_id in [*existing, *incoming]:
        if check_id in _CHECKS and check_id not in merged:
            merged.append(check_id)
    return merged
