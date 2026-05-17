"""Windows Update Failure workflow.

This workflow uses LangGraph as the control-flow backbone. Each conversational
turn builds a small graph state, invokes the graph, then persists the next
waiting state in the shared session store.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.models.schemas import AgentMessageResponse, UICard
from app.services.llm import llm_structured
from app.workflows.base import BaseWorkflow

_AFFIRMATIVE = {
    "yes",
    "y",
    "ok",
    "okay",
    "sure",
    "allow",
    "approve",
    "go ahead",
    "do it",
    "please do",
}
_NEGATIVE = {"no", "n", "cancel", "stop", "not now", "deny", "do not"}
_STILL_BROKEN = {
    "still",
    "same",
    "not fixed",
    "did not work",
    "doesn't work",
    "failed",
    "issue persists",
    "not working",
    "yes",
    "y",
}
_FIXED = {"fixed", "resolved", "working now", "it works", "done", "no"}
_FACT_PATTERNS = {
    "vpn_connected": (
        r"\b(vpn).*\b(connect(ed)?|on|working|ok|okay)\b|\b(connect(ed)?|on).*\b(vpn)\b",
        "VPN is connected",
    ),
    "internet_ok": (
        r"\b(internet|network|wifi|wi-fi|connection).*\b(ok|okay|stable|working|connected)\b|\b(connect(ed)?|stable).*\b(internet|network|wifi|wi-fi)\b",
        "internet connection is stable",
    ),
    "restarted": (
        r"\b(restart(ed)?|reboot(ed)?)\b",
        "device was restarted",
    ),
    "disk_space_checked": (
        r"\b(disk|space|storage).*\b(ok|okay|enough|available|free|checked)\b",
        "disk space was checked",
    ),
}

_FOLLOWUP_PROMPT = """You are classifying a user's reply inside a Windows Update failure troubleshooting workflow.
The assistant has already suggested user-side checks before asking for local system access.

Classify the reply as exactly one reply_type:
- partial_update: user reports a troubleshooting check or fact, but does not clearly say Windows Update is still failing or resolved.
- still_failing: user clearly says Windows Update is still failing, failed again, or the issue persists.
- resolved: user clearly says Windows Update is fixed or working now.
- approve_access: user explicitly allows local agent/system access.
- deny_access: user refuses local agent/system access.
- unclear: none of the above.

Known fact ids may include: vpn_connected, internet_ok, restarted, disk_space_checked.
Return a concise acknowledgement summary when useful.

Current workflow state: {session_state}
User reply: {message}
"""


class WindowsUpdateState(TypedDict, total=False):
    session_state: str
    user_message: str
    decision: Literal[
        "start",
        "partial_update",
        "resolved",
        "still_broken",
        "approve_access",
        "deny_access",
        "action_complete",
        "unclear",
    ]
    known_facts: list[str]
    summary: str
    response: AgentMessageResponse


class _FollowupClassification(BaseModel):
    reply_type: Literal[
        "partial_update",
        "still_failing",
        "resolved",
        "approve_access",
        "deny_access",
        "unclear",
    ]
    known_facts: list[str] = Field(default_factory=list)
    summary: str = ""


class WindowsUpdateFailureWorkflow(BaseWorkflow):
    workflow_id = "windows_update_failure"
    title = "Windows Update Failure"
    active = True

    def __init__(self) -> None:
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(WindowsUpdateState)
        graph.add_node("classify_turn", self._classify_turn)
        graph.add_node("suggest_user_fixes", self._suggest_user_fixes)
        graph.add_node("summarize_progress", self._summarize_progress)
        graph.add_node("request_local_access", self._request_local_access)
        graph.add_node("trigger_settings_action", self._trigger_settings_action)
        graph.add_node("finish", self._finish)
        graph.add_node("clarify", self._clarify)

        graph.set_entry_point("classify_turn")
        graph.add_conditional_edges(
            "classify_turn",
            self._route,
            {
                "suggest_user_fixes": "suggest_user_fixes",
                "summarize_progress": "summarize_progress",
                "request_local_access": "request_local_access",
                "trigger_settings_action": "trigger_settings_action",
                "finish": "finish",
                "clarify": "clarify",
            },
        )
        graph.add_edge("suggest_user_fixes", END)
        graph.add_edge("summarize_progress", END)
        graph.add_edge("request_local_access", END)
        graph.add_edge("trigger_settings_action", END)
        graph.add_edge("finish", END)
        graph.add_edge("clarify", END)
        return graph.compile()

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        if session.get("workflow") != self.workflow_id:
            session["workflow"] = self.workflow_id
            session["state"] = "idle"
            session["windows_update_facts"] = []
            session.pop("local_action_result", None)

        graph_state = self._graph.invoke(
            {
                "session_state": session.get("state", "idle"),
                "user_message": user_message or "",
                "known_facts": session.get("windows_update_facts") or [],
            }
        )
        session["windows_update_facts"] = _merge_facts(
            session.get("windows_update_facts") or [],
            graph_state.get("known_facts") or [],
        )
        response = graph_state["response"]
        session["state"] = response.state
        return response

    def _classify_turn(self, state: WindowsUpdateState) -> WindowsUpdateState:
        session_state = state.get("session_state") or "idle"
        lower = (state.get("user_message") or "").strip().lower()

        if session_state in ("idle", None):
            return {**state, "decision": "start"}
        if session_state == "awaiting_fix_result":
            classification = _classify_followup(session_state, lower)
            decision = (
                "still_broken"
                if classification.reply_type == "still_failing"
                else classification.reply_type
            )
            return {
                **state,
                "decision": decision,
                "known_facts": _merge_facts(
                    state.get("known_facts") or [],
                    classification.known_facts,
                ),
                "summary": classification.summary,
            }
        if session_state == "awaiting_access_approval":
            classification = _classify_followup(session_state, lower)
            if classification.reply_type in ("approve_access", "deny_access"):
                return {**state, "decision": classification.reply_type}
            return {**state, "decision": "unclear"}
        if session_state == "awaiting_settings_action":
            return {**state, "decision": "action_complete"}
        return {**state, "decision": "start"}

    @staticmethod
    def _route(state: WindowsUpdateState) -> str:
        decision = state.get("decision")
        if decision == "start":
            return "suggest_user_fixes"
        if decision == "partial_update":
            return "summarize_progress"
        if decision == "still_broken":
            return "request_local_access"
        if decision == "approve_access":
            return "trigger_settings_action"
        if decision in ("resolved", "deny_access", "action_complete"):
            return "finish"
        return "clarify"

    def _suggest_user_fixes(self, state: WindowsUpdateState) -> WindowsUpdateState:
        response = AgentMessageResponse(
            message=(
                "Let's try the common Windows Update fixes first:\n\n"
                "1. Confirm you are connected to VPN if your company requires it for updates.\n"
                "2. Check that your internet connection is stable.\n"
                "3. Restart the device, then try Windows Update again.\n"
                "4. Make sure there is enough free disk space for the update.\n\n"
                "After trying those, tell me whether the update is working or if the issue is still happening."
            ),
            workflow=self.workflow_id,
            state="awaiting_fix_result",
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "suggest_user_fixes",
                        "checks": [
                            "VPN connected if required",
                            "Internet connection stable",
                            "Device restarted",
                            "Disk space available",
                        ],
                    },
                )
            ],
        )
        return {**state, "response": response}

    def _summarize_progress(self, state: WindowsUpdateState) -> WindowsUpdateState:
        facts = state.get("known_facts") or []
        summary = (state.get("summary") or "").strip()
        if not summary:
            summary = _facts_summary(facts) or "I have noted that update."

        response = AgentMessageResponse(
            message=f"Thanks, I have noted that {summary}. Is Windows Update still failing after checking that?",
            workflow=self.workflow_id,
            state="awaiting_fix_result",
            cards=[
                UICard(
                    kind="workflow",
                    data={
                        "title": self.title,
                        "step": "summarize_progress",
                        "known_facts": facts,
                    },
                )
            ],
        )
        return {**state, "response": response}

    def _request_local_access(self, state: WindowsUpdateState) -> WindowsUpdateState:
        response = AgentMessageResponse(
            message=(
                "Thanks for checking. The next step needs local workstation access. "
                "Allow agent to access this device and open Windows Update settings?"
            ),
            workflow=self.workflow_id,
            state="awaiting_access_approval",
            cards=[
                UICard(
                    kind="confirmation",
                    data={
                        "title": "Allow local agent access?",
                        "action": "open_windows_update_settings",
                        "scope": "Open Windows Update settings only",
                    },
                )
            ],
        )
        return {**state, "response": response}

    def _trigger_settings_action(self, state: WindowsUpdateState) -> WindowsUpdateState:
        response = AgentMessageResponse(
            message="I'll ask the local app server to open Windows Update settings now.",
            workflow=self.workflow_id,
            state="awaiting_settings_action",
            metadata={
                "trigger_local_app_action": {
                    "action": "open_windows_update_settings",
                    "device_name": "LOCAL-ENDPOINT",
                }
            },
            requires_input=False,
        )
        return {**state, "response": response}

    def _finish(self, state: WindowsUpdateState) -> WindowsUpdateState:
        decision = state.get("decision")
        if decision == "resolved":
            message = "Great, Windows Update is working now. I'll close this workflow."
        elif decision == "deny_access":
            message = "No problem. I will not access the device. You can restart this workflow if you want to try again later."
        else:
            message = (
                "Windows Update settings should be open now. Please review the update error there "
                "and try running the update again."
            )
        response = AgentMessageResponse(
            message=message,
            workflow=self.workflow_id,
            state="complete",
            requires_input=False,
        )
        return {**state, "response": response}

    def _clarify(self, state: WindowsUpdateState) -> WindowsUpdateState:
        session_state = state.get("session_state")
        if session_state == "awaiting_access_approval":
            message = "Please reply 'yes' to allow opening Windows Update settings, or 'no' to stop."
            next_state = "awaiting_access_approval"
        else:
            message = "Is Windows Update working now, or is the issue still happening?"
            next_state = "awaiting_fix_result"
        response = AgentMessageResponse(
            message=message,
            workflow=self.workflow_id,
            state=next_state,
        )
        return {**state, "response": response}


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


def _classify_followup(
    session_state: str, message: str
) -> _FollowupClassification:
    llm_result = llm_structured(
        _FOLLOWUP_PROMPT.format(session_state=session_state, message=message),
        _FollowupClassification,
    )
    if llm_result is not None:
        return _normalize_classification(llm_result, session_state, message)
    return _fallback_classify_followup(session_state, message)


def _normalize_classification(
    result: _FollowupClassification, session_state: str, message: str
) -> _FollowupClassification:
    fallback = _fallback_classify_followup(session_state, message)
    facts = _merge_facts(result.known_facts, fallback.known_facts)

    # Guardrail: do not let generic approvals during the fix stage skip guidance.
    reply_type = result.reply_type
    if session_state == "awaiting_fix_result" and reply_type == "approve_access":
        reply_type = fallback.reply_type
    if session_state == "awaiting_access_approval" and reply_type not in (
        "approve_access",
        "deny_access",
    ):
        reply_type = fallback.reply_type

    summary = result.summary.strip() or fallback.summary
    return _FollowupClassification(
        reply_type=reply_type,
        known_facts=facts,
        summary=summary,
    )


def _fallback_classify_followup(
    session_state: str, message: str
) -> _FollowupClassification:
    facts = _extract_known_facts(message)

    if session_state == "awaiting_access_approval":
        if _has_phrase(message, _AFFIRMATIVE):
            return _FollowupClassification(reply_type="approve_access")
        if _has_phrase(message, _NEGATIVE):
            return _FollowupClassification(reply_type="deny_access")
        return _FollowupClassification(reply_type="unclear")

    if _has_phrase(message, _STILL_BROKEN):
        return _FollowupClassification(
            reply_type="still_failing",
            known_facts=facts,
            summary=_facts_summary(facts),
        )
    if facts:
        return _FollowupClassification(
            reply_type="partial_update",
            known_facts=facts,
            summary=_facts_summary(facts),
        )
    if _has_phrase(message, _FIXED):
        return _FollowupClassification(reply_type="resolved")
    return _FollowupClassification(reply_type="unclear")


def _extract_known_facts(message: str) -> list[str]:
    facts: list[str] = []
    for fact_id, (pattern, _) in _FACT_PATTERNS.items():
        if re.search(pattern, message):
            facts.append(fact_id)
    return facts


def _facts_summary(facts: list[str]) -> str:
    labels = [
        _FACT_PATTERNS[fact_id][1]
        for fact_id in facts
        if fact_id in _FACT_PATTERNS
    ]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _merge_facts(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    for fact in [*existing, *incoming]:
        if fact in _FACT_PATTERNS and fact not in merged:
            merged.append(fact)
    return merged
