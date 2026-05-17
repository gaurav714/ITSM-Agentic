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
from typing import Any, Dict, Literal

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from app.models.schemas import AgentMessageResponse, UICard
from app.services.llm import llm_structured
from app.services.ticket_service import create_ticket
from app.workflows.base import BaseWorkflow
from app.workflows.system_slow.agent import run_system_slow_agent
from app.workflows.system_slow.prompts import CONFIRMATION_PROMPT
from app.workflows.system_slow.state import SystemSlowState

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


class _Confirmation(BaseModel):
    decision: Literal["confirm", "cancel", "unclear"]


class SystemSlowWorkflow(BaseWorkflow):
    workflow_id = "system_slow_diagnostics"
    title = "System Slow Diagnostics"
    active = True

    def __init__(self) -> None:
        self._graph = self._build_graph()

    # -- LangGraph wiring (kept lightweight; main path is `handle`) ----------
    def _build_graph(self):
        sg = StateGraph(SystemSlowState)

        def collect_device(state: SystemSlowState) -> SystemSlowState:
            return state

        def diagnostic_router_node(state: SystemSlowState) -> SystemSlowState:
            return state

        def normalize_node(state: SystemSlowState) -> SystemSlowState:
            return state

        def summary_node(state: SystemSlowState) -> SystemSlowState:
            return state

        sg.add_node("collect_device_name", collect_device)
        sg.add_node("diagnostic_router", diagnostic_router_node)
        sg.add_node("normalize_results", normalize_node)
        sg.add_node("generate_summary", summary_node)
        sg.set_entry_point("collect_device_name")
        sg.add_edge("collect_device_name", "diagnostic_router")
        sg.add_edge("diagnostic_router", "normalize_results")
        sg.add_edge("normalize_results", "generate_summary")
        sg.add_edge("generate_summary", END)
        return sg.compile()

    # -- Conversational handler ---------------------------------------------
    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        state = session.get("state", "idle")
        msg = (user_message or "").strip()
        lower = msg.lower()

        # Entry — first time hitting this workflow.
        if state in ("idle", None) or session.get("workflow") != self.workflow_id:
            session["workflow"] = self.workflow_id
            return self._start_local_app_diagnostics(session)

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
    def _start_local_app_diagnostics(
        self, session: Dict[str, Any]
    ) -> AgentMessageResponse:
        device_name = session.get("device_name") or _LOCAL_DEVICE_PLACEHOLDER
        session["device_name"] = device_name
        session["diagnostic_id"] = f"DIAG-{uuid.uuid4().hex[:8].upper()}"
        session["state"] = "awaiting_browser_diagnostics"

        return AgentMessageResponse(
            message=(
                "I can help diagnose system slowness. I'll ask the browser to query "
                "the local app server running on this system and collect diagnostics — one moment."
            ),
            workflow=self.workflow_id,
            state="awaiting_browser_diagnostics",
            cards=[
                UICard(
                    kind="diagnostic_status",
                    data={
                        "diagnostic_id": session["diagnostic_id"],
                        "method": "local_app",
                        "status": "collecting_local_app_metrics",
                        "device_name": device_name,
                    },
                )
            ],
            metadata={"trigger_browser_diagnostics": True},
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
                    "Reply 'yes' to close Edge using the local app server, "
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
                message="I'll ask the local app server to close Microsoft Edge now.",
                workflow=self.workflow_id,
                state="awaiting_remediation_action",
                metadata={
                    "trigger_local_app_action": {
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
                    "I did not receive a result from the local app server. "
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

