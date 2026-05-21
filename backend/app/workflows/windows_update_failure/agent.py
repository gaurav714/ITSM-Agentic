"""Tool-using intent and decision agent for Windows Update troubleshooting."""

from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.services.llm import llm_client


def run_windows_update_decision_agent(context: Dict[str, Any]) -> Dict[str, Any]:
    """Let a ReAct agent interpret the user and choose the next workflow action."""
    llm = llm_client()
    if llm is None:
        return {
            "agentic": False,
            "llm_called": False,
            "agent_error": "llm_unavailable: OPENAI_API_KEY/OPENAI_MODEL is not configured or the LLM client could not be created.",
            "decision": None,
            "trace": [],
            "summary": "",
        }

    trace: list[dict] = []
    tools = _build_decision_tools(trace)
    agent = create_react_agent(
        llm,
        tools,
        messages_modifier=(
            "You are a Windows Update troubleshooting supervisor. Interpret the "
            "latest user message and the workflow context yourself. Then call "
            "exactly one provided decision tool. Do not answer directly. You may "
            "choose only from the available_checks and allowlisted_tools in the "
            "context. If awaiting_local_access_approval=true, the latest user "
            "message is the answer to your permission request: clear approval "
            "must choose run_tool with recommended_first_tool, denial or cancel "
            "must choose stop_workflow, and ambiguity must choose clarify. Never "
            "choose request_access while awaiting_local_access_approval=true. "
            "If the user asks to launch, check, use, or run the local agent and "
            "access is not approved, choose request_access. After multiple checks "
            "are discussed, or the user says the issue is still failing, prefer "
            "request_access over repeating basic checks. Do not ask for a check "
            "already present in checks_discussed. Keep assistant messages concise "
            "and natural."
        ),
    )

    objective = {
        "task": "interpret_user_and_choose_next_windows_update_workflow_action",
        "decision_tools": {
            "ask_check": "Ask the user for one next troubleshooting check.",
            "request_access": "Ask for explicit local workstation access.",
            "run_tool": "Run an allowlisted local tool after approval is already stored or the current awaiting-approval user reply clearly grants permission.",
            "mark_resolved": "Close because the user says Windows Update is fixed.",
            "stop_workflow": "Close because the user cancelled or denied access.",
            "clarify": "Ask a focused clarification question.",
        },
        "context": context,
    }

    try:
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "Interpret the user's intent and choose the next safe "
                            "workflow action by calling exactly one decision tool:\n"
                            + json.dumps(objective, indent=2)
                        )
                    )
                ]
            }
        )
    except Exception as exc:
        return {
            "agentic": False,
            "llm_called": True,
            "agent_error": str(exc),
            "decision": None,
            "trace": trace,
            "summary": "",
        }

    final_message = result["messages"][-1].content if result.get("messages") else ""
    decision = trace[-1] if trace else None
    if not decision:
        return {
            "agentic": False,
            "llm_called": True,
            "agent_error": "llm_no_decision_tool_call: model did not call a workflow decision tool.",
            "decision": None,
            "trace": trace,
            "summary": final_message,
        }
    return {
        "agentic": True,
        "llm_called": True,
        "decision": decision,
        "trace": trace,
        "summary": final_message,
    }


def _build_decision_tools(trace: list[dict]):
    @tool
    def ask_check(check_id: str, message: str, rationale: str = "") -> Dict[str, Any]:
        """Ask the user to perform one Windows Update troubleshooting check."""
        event = {
            "decision": "ask_check",
            "selected_check": check_id,
            "selected_tool": "",
            "message": message,
            "rationale": rationale,
        }
        trace.append(event)
        return event

    @tool
    def request_access(message: str, rationale: str = "") -> Dict[str, Any]:
        """Ask for explicit permission before any local tool can run."""
        event = {
            "decision": "request_access",
            "selected_check": "",
            "selected_tool": "",
            "message": message,
            "rationale": rationale,
        }
        trace.append(event)
        return event

    @tool
    def run_tool(tool_name: str, rationale: str = "") -> Dict[str, Any]:
        """Select an already-approved allowlisted local tool to run."""
        event = {
            "decision": "run_tool",
            "selected_check": "",
            "selected_tool": tool_name,
            "message": "",
            "rationale": rationale,
        }
        trace.append(event)
        return event

    @tool
    def mark_resolved(message: str, rationale: str = "") -> Dict[str, Any]:
        """Close the workflow because the user reports Windows Update is fixed."""
        event = {
            "decision": "resolved",
            "selected_check": "",
            "selected_tool": "",
            "message": message,
            "rationale": rationale,
        }
        trace.append(event)
        return event

    @tool
    def stop_workflow(message: str, rationale: str = "") -> Dict[str, Any]:
        """Close the workflow because the user denied access or cancelled."""
        event = {
            "decision": "deny_or_cancel",
            "selected_check": "",
            "selected_tool": "",
            "message": message,
            "rationale": rationale,
        }
        trace.append(event)
        return event

    @tool
    def clarify(message: str, rationale: str = "") -> Dict[str, Any]:
        """Ask a focused clarification question."""
        event = {
            "decision": "clarify",
            "selected_check": "",
            "selected_tool": "",
            "message": message,
            "rationale": rationale,
        }
        trace.append(event)
        return event

    return [
        ask_check,
        request_access,
        run_tool,
        mark_resolved,
        stop_workflow,
        clarify,
    ]
