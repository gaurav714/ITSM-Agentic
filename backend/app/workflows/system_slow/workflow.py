"""System Slow Diagnostics workflow.

Implemented as a conversational state machine over the session store.
LangGraph is wired in for visualization/extensibility, while the confirmed
diagnostic execution step is delegated to `system_slow.agent`.

Agentic touches (active when OPENAI_API_KEY is set):
- LLM classifies the user's confirmation reply.
- A LangGraph ReAct agent selects and runs diagnostic tools.
- LLM writes the diagnostic summary and ticket draft in natural language.
Each LLM call has a deterministic fallback so the workflow keeps working
when the LLM is unavailable.
"""

from __future__ import annotations

import uuid
import re
from typing import Any, Dict, Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.models.schemas import AgentMessageResponse, UICard
from app.services.llm import llm_structured
from app.services.ticket_service import create_ticket
from app.services.workflow_turn_agent import agent_metadata, choose_workflow_tool
from app.workflows.base import BaseWorkflow
from app.workflows.system_slow.agent import run_system_slow_agent
from app.workflows.system_slow.prompts import CONFIRMATION_PROMPT, TRIAGE_CLASSIFY_PROMPT

_AFFIRMATIVE = {
    "yes",
    "y",
    "confirm",
    "create",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "do it",
    "file it",
    "please do",
}
_NEGATIVE = {"no", "n", "cancel", "stop", "abort", "never mind", "not now"}
_LOCAL_DEVICE_PLACEHOLDER = "LOCAL-ENDPOINT"
_READY_TO_DIAGNOSE = {
    "yes",
    "y",
    "still",
    "same",
    "still slow",
    "still lagging",
    "not fixed",
    "not working",
    "check",
    "diagnose",
    "diagnostics",
    "run it",
    "go ahead",
}
_RESOLVED = {"fixed", "resolved", "working now", "fine now", "better now", "no"}
_TRIAGE_FACT_PATTERNS = {
    "affected_app": (
        r"\b(edge|chrome|browser|outlook|teams|excel|word|app|application)\b",
        "a specific app appears affected",
    ),
    "all_apps": (
        r"\b(all apps|everything|whole system|entire system|all programs)\b",
        "the slowness affects the whole system",
    ),
    "started_recently": (
        r"\b(just started|recently|after update|after reboot|since morning)\b",
        "the issue started recently",
    ),
    "started_today": (
        r"\b(today|this morning|now|right now)\b",
        "the issue started today",
    ),
    "restarted": (r"\b(restart(ed)?|reboot(ed)?)\b", "the device was restarted"),
    "closed_apps": (
        r"\b(closed apps|close apps|closed browser|closed tabs|quit apps)\b",
        "apps were closed to reduce load",
    ),
    "high_impact": (
        r"\b(can't work|cannot work|unusable|freezing|hang(ing)?|stuck)\b",
        "the issue is disrupting work",
    ),
}


class _Confirmation(BaseModel):
    decision: Literal["confirm", "cancel", "unclear"]


class _TriageClassification(BaseModel):
    reply_type: Literal["partial_update", "ready_to_diagnose", "resolved", "unclear"]
    known_facts: list[str] = Field(default_factory=list)
    summary: str = ""
    selected_tool: str = "deterministic_fallback"


class SystemSlowTriageState(TypedDict, total=False):
    session_state: str
    user_message: str
    decision: Literal[
        "start",
        "partial_update",
        "ready_to_diagnose",
        "resolved",
        "unclear",
    ]
    known_facts: list[str]
    summary: str
    response: AgentMessageResponse


class SystemSlowWorkflow(BaseWorkflow):
    workflow_id = "system_slow_diagnostics"
    title = "System Slow Diagnostics"
    active = True

    def __init__(self) -> None:
        self._graph = self._build_graph()

    # -- LangGraph wiring (kept lightweight; main path is `handle`) ----------
    def _build_graph(self):
        graph = StateGraph(SystemSlowTriageState)
        graph.add_node("classify_turn", self._classify_triage_turn)
        graph.add_node("start_triage", self._start_triage)
        graph.add_node("summarize_triage", self._summarize_triage)
        graph.add_node("trigger_diagnostics", self._trigger_diagnostics)
        graph.add_node("finish_resolved", self._finish_resolved)
        graph.add_node("clarify_triage", self._clarify_triage)

        graph.set_entry_point("classify_turn")
        graph.add_conditional_edges(
            "classify_turn",
            self._route_triage,
            {
                "start_triage": "start_triage",
                "summarize_triage": "summarize_triage",
                "trigger_diagnostics": "trigger_diagnostics",
                "finish_resolved": "finish_resolved",
                "clarify_triage": "clarify_triage",
            },
        )
        graph.add_edge("start_triage", END)
        graph.add_edge("summarize_triage", END)
        graph.add_edge("trigger_diagnostics", END)
        graph.add_edge("finish_resolved", END)
        graph.add_edge("clarify_triage", END)
        return graph.compile()

    # -- Conversational handler ---------------------------------------------
    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        state = session.get("state", "idle")
        msg = (user_message or "").strip()
        lower = msg.lower()

        # Entry — first time hitting this workflow.
        if session.get("workflow") != self.workflow_id:
            session["workflow"] = self.workflow_id
            session["state"] = "idle"
            session["system_slow_facts"] = []
            session.pop("local_action_result", None)
            state = "idle"

        if state in ("idle", None) or state == "awaiting_triage":
            graph_state = self._graph.invoke(
                {
                    "session_state": session.get("state", "idle"),
                    "user_message": msg,
                    "known_facts": session.get("system_slow_facts") or [],
                }
            )
            session["system_slow_facts"] = _merge_facts(
                session.get("system_slow_facts") or [],
                graph_state.get("known_facts") or [],
            )
            response = graph_state["response"]
            if response.state == "awaiting_browser_diagnostics":
                response = self._copy_diagnostic_start_to_session(session, response)
            session["state"] = response.state
            return response

        if state == "awaiting_browser_diagnostics":
            # User is signalling that browser diagnostics have been pushed.
            return self._run_diagnostics_and_summarize(session)

        if state == "awaiting_remediation_confirmation":
            return self._handle_remediation_confirmation(session, lower)

        if state == "awaiting_remediation_action":
            return self._handle_remediation_action_result(session)

        if state == "awaiting_confirmation":
            return self._handle_confirmation(session, lower)

        if state == "complete":
            return AgentMessageResponse(
                message=(
                    f"Your previous ticket {session.get('ticket_id')} is on file. "
                    "Describe a new issue to start over."
                ),
                workflow=self.workflow_id,
                state="complete",
                requires_input=False,
            )

        # Fallback
        return AgentMessageResponse(
            message="Could you describe the issue again?",
            workflow=self.workflow_id,
            state=state or "idle",
        )

    # -- Helpers -------------------------------------------------------------
    def _classify_triage_turn(
        self, state: SystemSlowTriageState
    ) -> SystemSlowTriageState:
        session_state = state.get("session_state") or "idle"
        lower = (state.get("user_message") or "").strip().lower()

        if session_state in ("idle", None):
            return {**state, "decision": "start"}

        classification = _classify_triage_followup(session_state, lower)
        return {
            **state,
            "decision": classification.reply_type,
            "known_facts": _merge_facts(
                state.get("known_facts") or [], classification.known_facts
            ),
            "summary": classification.summary,
        }

    @staticmethod
    def _route_triage(state: SystemSlowTriageState) -> str:
        decision = state.get("decision")
        if decision == "start":
            return "start_triage"
        if decision == "partial_update":
            return "summarize_triage"
        if decision == "ready_to_diagnose":
            return "trigger_diagnostics"
        if decision == "resolved":
            return "finish_resolved"
        return "clarify_triage"

    def _start_triage(self, state: SystemSlowTriageState) -> SystemSlowTriageState:
        response = AgentMessageResponse(
            message=(
                "I can help with the slowness. Before I run diagnostics, tell me "
                "what you are seeing: did it start today, is it one app or the "
                "whole system, and have you already tried restarting or closing "
                "heavy apps?"
            ),
            workflow=self.workflow_id,
            state="awaiting_triage",
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "guided_triage",
                        "checks": [
                            "When the slowness started",
                            "One app vs whole system",
                            "Restart or app cleanup already tried",
                        ],
                    },
                )
            ],
            metadata=_metadata("request_more_context"),
        )
        return {**state, "response": response}

    def _summarize_triage(
        self, state: SystemSlowTriageState
    ) -> SystemSlowTriageState:
        facts = state.get("known_facts") or []
        summary = (state.get("summary") or "").strip()
        if not summary:
            summary = _facts_summary(facts) or "that context"

        response = AgentMessageResponse(
            message=(
                f"Thanks, I noted {summary}. Is the device still slow right now? "
                "Reply 'yes' and I will run local diagnostics, or tell me if it is fixed."
            ),
            workflow=self.workflow_id,
            state="awaiting_triage",
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "triage_context",
                        "known_facts": facts,
                    },
                )
            ],
            metadata=_metadata(state.get("decision")),
        )
        return {**state, "response": response}

    def _trigger_diagnostics(
        self, state: SystemSlowTriageState
    ) -> SystemSlowTriageState:
        response = self._start_backend_local_diagnostics({})
        return {**state, "response": response}

    def _finish_resolved(
        self, state: SystemSlowTriageState
    ) -> SystemSlowTriageState:
        response = AgentMessageResponse(
            message="Good to hear it is working now. I will close this diagnostic workflow.",
            workflow=self.workflow_id,
            state="complete",
            metadata=_metadata("finish_workflow"),
            requires_input=False,
        )
        return {**state, "response": response}

    def _clarify_triage(
        self, state: SystemSlowTriageState
    ) -> SystemSlowTriageState:
        response = AgentMessageResponse(
            message=(
                "Is the device still slow right now? If yes, tell me whether it is "
                "one app or the whole system and I will run diagnostics."
            ),
            workflow=self.workflow_id,
            state="awaiting_triage",
            metadata=_metadata("request_more_context"),
        )
        return {**state, "response": response}

    def _copy_diagnostic_start_to_session(
        self, session: Dict[str, Any], response: AgentMessageResponse
    ) -> AgentMessageResponse:
        diagnostic_card = next(
            (card for card in response.cards if card.kind == "diagnostic_status"),
            None,
        )
        data = diagnostic_card.data if diagnostic_card else {}
        session["device_name"] = data.get("device_name") or _LOCAL_DEVICE_PLACEHOLDER
        session["diagnostic_id"] = data.get("diagnostic_id")
        return response

    def _start_backend_local_diagnostics(
        self, session: Dict[str, Any]
    ) -> AgentMessageResponse:
        device_name = session.get("device_name") or _LOCAL_DEVICE_PLACEHOLDER
        session["device_name"] = device_name
        session["diagnostic_id"] = f"DIAG-{uuid.uuid4().hex[:8].upper()}"
        session["state"] = "awaiting_browser_diagnostics"

        return AgentMessageResponse(
            message=(
                "I can help diagnose system slowness. I'll collect browser telemetry "
                "and run backend-local diagnostics on this workstation - one moment."
            ),
            workflow=self.workflow_id,
            state="awaiting_browser_diagnostics",
            cards=[
                UICard(
                    kind="diagnostic_status",
                    data={
                        "diagnostic_id": session["diagnostic_id"],
                        "method": "backend_local",
                        "status": "collecting_backend_local_metrics",
                        "device_name": device_name,
                    },
                )
            ],
            metadata={
                **_metadata("start_diagnostics"),
                "trigger_browser_diagnostics": True,
            },
            requires_input=False,
        )

    def _run_diagnostics_and_summarize(
        self, session: Dict[str, Any]
    ) -> AgentMessageResponse:
        device_name = session["device_name"]
        agent_result = run_system_slow_agent(
            device_name,
            session["session_id"],
            session["diagnostic_id"],
        )
        diagnostic = agent_result["diagnostic"]
        summary = agent_result["summary"]
        draft = agent_result["ticket_draft"]
        device_name = agent_result.get("device_name") or device_name
        session["device_name"] = device_name
        session["diagnostic_agent_result"] = agent_result
        session["diagnostic"] = diagnostic
        session["summary"] = summary
        session["ticket_draft"] = draft

        if self._edge_stop_available(diagnostic):
            session["state"] = "awaiting_remediation_confirmation"
            return AgentMessageResponse(
                message=(
                    f"{summary}\n\nMicrosoft Edge appears to be running. "
                    "Reply 'yes' to close Edge using backend-local tools, "
                    "or 'no' to skip this step."
                ),
                workflow=self.workflow_id,
                state="awaiting_remediation_confirmation",
                cards=[
                    UICard(
                        kind="diagnostic_result",
                        data={
                            "diagnostic_id": session["diagnostic_id"],
                            "device_name": device_name,
                            "method": diagnostic.get("method"),
                            "metrics": diagnostic,
                            "summary": summary,
                            "agentic": agent_result["agentic"],
                            "agent_summary": agent_result["agent_summary"],
                            "tool_trace": agent_result["tool_trace"],
                        },
                    )
                ],
            )

        session["state"] = "awaiting_confirmation"

        return AgentMessageResponse(
            message=(
                f"{summary}\n\nI did not find a supported local action to run. I've prepared a support ticket draft. "
                "Reply 'yes' to create it, or 'no' to cancel."
            ),
            workflow=self.workflow_id,
            state="awaiting_confirmation",
            cards=[
                UICard(
                    kind="diagnostic_result",
                    data={
                        "diagnostic_id": session["diagnostic_id"],
                        "device_name": device_name,
                        "method": diagnostic.get("method"),
                        "metrics": diagnostic,
                        "summary": summary,
                        "agentic": agent_result["agentic"],
                        "agent_summary": agent_result["agent_summary"],
                        "tool_trace": agent_result["tool_trace"],
                    },
                ),
                UICard(kind="ticket_draft", data=draft),
            ],
        )

    def _handle_remediation_confirmation(
        self, session: Dict[str, Any], lower: str
    ) -> AgentMessageResponse:
        decision = self._classify_confirmation(lower)

        if decision == "confirm":
            session["state"] = "awaiting_remediation_action"
            session.pop("local_action_result", None)
            return AgentMessageResponse(
                message="I'll ask the backend-local tools to close Microsoft Edge now.",
                workflow=self.workflow_id,
                state="awaiting_remediation_action",
                metadata={
                    "trigger_backend_action": {
                        "action": "stop_edge",
                        "diagnostic_id": session.get("diagnostic_id"),
                        "device_name": session.get("device_name"),
                    }
                },
                requires_input=False,
            )

        if decision == "cancel":
            session["state"] = "awaiting_confirmation"
            return self._offer_ticket_after_remediation(
                session,
                "Skipped closing Microsoft Edge. If the issue persists, I can create a support ticket."
            )

        return AgentMessageResponse(
            message="Please reply 'yes' to close Microsoft Edge or 'no' to skip this step.",
            workflow=self.workflow_id,
            state="awaiting_remediation_confirmation",
        )

    def _handle_remediation_action_result(
        self, session: Dict[str, Any]
    ) -> AgentMessageResponse:
        result = session.get("local_action_result") or {}
        session["state"] = "awaiting_confirmation"

        if not result:
            return AgentMessageResponse(
                message=(
                    "I did not receive a result from the backend-local action. "
                    "Reply 'yes' to create a support ticket, or 'no' to cancel."
                ),
                workflow=self.workflow_id,
                state="awaiting_confirmation",
                cards=[UICard(kind="ticket_draft", data=session["ticket_draft"])],
            )

        stopped = result.get("stopped_processes") or []
        detail = (
            f"{result.get('message', 'Local action completed')} "
            f"Stopped processes: {', '.join(stopped)}."
            if stopped
            else result.get("message", "Local action completed.")
        )
        return self._offer_ticket_after_remediation(
            session,
            f"{detail} If the system is still slow, I can create a support ticket.",
        )

    def _offer_ticket_after_remediation(
        self, session: Dict[str, Any], message: str
    ) -> AgentMessageResponse:
        return AgentMessageResponse(
            message=f"{message} Reply 'yes' to create it, or 'no' to cancel.",
            workflow=self.workflow_id,
            state="awaiting_confirmation",
            cards=[UICard(kind="ticket_draft", data=session["ticket_draft"])],
        )

    def _handle_confirmation(
        self, session: Dict[str, Any], lower: str
    ) -> AgentMessageResponse:
        decision = self._classify_confirmation(lower)

        if decision == "confirm":
            from app.models.schemas import TicketDraft  # local to avoid cycles

            draft = TicketDraft(**session["ticket_draft"])
            ticket = create_ticket(draft)
            session["ticket_id"] = ticket["ticket_id"]
            session["state"] = "complete"
            return AgentMessageResponse(
                message=(
                    f"Ticket {ticket['ticket_id']} created successfully. "
                    "An IT engineer will follow up shortly."
                ),
                workflow=self.workflow_id,
                state="complete",
                cards=[UICard(kind="ticket_created", data=ticket)],
                requires_input=False,
            )

        if decision == "cancel":
            session["state"] = "idle"
            session["ticket_draft"] = None
            return AgentMessageResponse(
                message="No ticket created. Let me know if you'd like to try again.",
                workflow=self.workflow_id,
                state="idle",
                requires_input=False,
            )

        return AgentMessageResponse(
            message="Please reply 'yes' to create the ticket or 'no' to cancel.",
            workflow=self.workflow_id,
            state="awaiting_confirmation",
        )

    # -- LLM-assisted helpers (each has a deterministic fallback) ------------
    @staticmethod
    def _classify_confirmation(lower: str) -> Literal["confirm", "cancel", "unclear"]:
        # Cheap keyword path first — avoids an LLM round-trip for the common case.
        if any(tok == lower or tok in lower.split() for tok in _AFFIRMATIVE):
            return "confirm"
        if any(tok == lower or tok in lower.split() for tok in _NEGATIVE):
            return "cancel"

        result = llm_structured(
            CONFIRMATION_PROMPT.format(message=lower),
            _Confirmation,
        )
        if result is not None:
            return result.decision
        return "unclear"

    @staticmethod
    def _edge_stop_available(diagnostic: Dict[str, Any]) -> bool:
        if diagnostic.get("edge_running"):
            return True
        for action in diagnostic.get("remediation_actions") or []:
            if (
                isinstance(action, dict)
                and action.get("id") == "stop_edge"
                and action.get("available")
            ):
                return True
        return False


def _classify_triage_followup(
    session_state: str, message: str
) -> _TriageClassification:
    selected = choose_workflow_tool(
        agent_name="system_slow_conversation_agent",
        system_prompt=(
            "You are a tool-constrained IT helpdesk workflow agent for system "
            "slowness. Choose exactly one provided tool. Do not invent actions. "
            "Use start_diagnostics only when the user says the issue is still "
            "happening or asks to diagnose."
        ),
        objective={
            "session_state": session_state,
            "user_message": message,
            "guardrails": [
                "Do not create tickets without explicit confirmation.",
                "Do not run remediation without explicit approval.",
            ],
        },
        tool_options={
            "record_triage_context": "Record useful slowness context and ask whether the issue is still happening.",
            "request_more_context": "Ask for missing slowness context before diagnostics.",
            "start_diagnostics": "Start backend-local diagnostics for an ongoing slowness issue.",
            "finish_workflow": "Close the workflow because the user says the issue is resolved.",
        },
    )
    if selected:
        return _classification_from_agent_tool(selected["tool"], message)

    llm_result = llm_structured(
        TRIAGE_CLASSIFY_PROMPT.format(session_state=session_state, message=message),
        _TriageClassification,
    )
    if llm_result is not None:
        return _normalize_triage_classification(llm_result, session_state, message)
    return _fallback_classify_triage(message)


def _classification_from_agent_tool(tool_name: str, message: str) -> _TriageClassification:
    facts = _extract_known_facts(message)
    mapping = {
        "record_triage_context": "partial_update",
        "request_more_context": "unclear",
        "start_diagnostics": "ready_to_diagnose",
        "finish_workflow": "resolved",
    }
    return _TriageClassification(
        reply_type=mapping.get(tool_name, "unclear"),
        known_facts=facts,
        summary=_facts_summary(facts),
        selected_tool=tool_name,
    )


def _normalize_triage_classification(
    result: _TriageClassification, session_state: str, message: str
) -> _TriageClassification:
    fallback = _fallback_classify_triage(message)
    facts = _merge_facts(result.known_facts, fallback.known_facts)
    reply_type = result.reply_type
    if session_state == "awaiting_triage" and reply_type == "unclear":
        reply_type = fallback.reply_type
    summary = result.summary.strip() or fallback.summary
    return _TriageClassification(
        reply_type=reply_type,
        known_facts=facts,
        summary=summary,
        selected_tool=result.selected_tool,
    )


def _fallback_classify_triage(message: str) -> _TriageClassification:
    facts = _extract_known_facts(message)
    if _has_phrase(message, _READY_TO_DIAGNOSE):
        return _TriageClassification(
            reply_type="ready_to_diagnose",
            known_facts=facts,
            summary=_facts_summary(facts),
            selected_tool="start_diagnostics",
        )
    if _has_phrase(message, _RESOLVED):
        return _TriageClassification(
            reply_type="resolved",
            known_facts=facts,
            selected_tool="finish_workflow",
        )
    if facts or message:
        return _TriageClassification(
            reply_type="partial_update",
            known_facts=facts,
            summary=_facts_summary(facts) or "the symptom details",
            selected_tool="record_triage_context",
        )
    return _TriageClassification(reply_type="unclear")


def _extract_known_facts(message: str) -> list[str]:
    facts: list[str] = []
    for fact_id, (pattern, _) in _TRIAGE_FACT_PATTERNS.items():
        if re.search(pattern, message):
            facts.append(fact_id)
    return facts


def _facts_summary(facts: list[str]) -> str:
    labels = [
        _TRIAGE_FACT_PATTERNS[fact_id][1]
        for fact_id in facts
        if fact_id in _TRIAGE_FACT_PATTERNS
    ]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _merge_facts(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for fact in [*existing, *incoming]:
        if fact in _TRIAGE_FACT_PATTERNS and fact not in merged:
            merged.append(fact)
    return merged


def _has_phrase(text: str, phrases: set[str]) -> bool:
    if not text:
        return False
    for phrase in phrases:
        if phrase == text:
            return True
        if len(phrase) <= 3:
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return True
            continue
        if phrase in text:
            return True
    return False


def _metadata(next_action: str | None) -> Dict[str, Any]:
    trace = []
    if next_action:
        trace.append({"tool": next_action, "status": "selected"})
    return agent_metadata("system_slow_conversation_agent", trace, next_action)

