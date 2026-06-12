"""Intent router — classifies a user message into a workflow id.

Uses an LLM when `OPENAI_API_KEY` is set, otherwise falls back to a keyword
heuristic that's sufficient for iteration 1 acceptance criteria.
"""

from __future__ import annotations

import re
from typing import Optional

from app.config import get_settings
from app.workflows.system_slow.prompts import INTENT_CLASSIFY_PROMPT

_LOCAL_APP_ISSUE_PATTERN = re.compile(
    r"\b(chrome|edge|firefox|browser|teams|outlook|word|excel|app|application)\b"
    r".{0,50}\b(not\s+working|not\s+opening|not\s+responding|not\s+launching|"
    r"won'?t\s+open|unable\s+to\s+open|crash(?:es|ing)?|broken|failing|failed)\b"
    r"|\b(app|application|browser)\b.{0,30}\b(not\s+launching|not\s+opening|not\s+responding)\b",
    re.I,
)

_EXPLICIT_OUTAGE_PATTERN = re.compile(
    r"\b(application\s+outage|service\s+down|outage|down\s+for\s+everyone|"
    r"all\s+users|many\s+users|multiple\s+users|company[-\s]?wide|org[-\s]?wide)\b",
    re.I,
)

_LOCAL_SYSTEM_QUERY_PATTERN = re.compile(
    r"\b(disk\s+(space|usage|free)|free\s+space|c\s*drive|windows\s+version|"
    r"os\s+version|top\s+process(?:es)?|running\s+process(?:es)?|services?|"
    r"memory\s+usage|ram\s+usage|cpu\s+usage|processor\s+usage|workstation|"
    r"current\s+(time|date|user)|system\s+(time|date)|timezone|time\s+zone|"
    r"host\s*name|hostname|computer\s+name|pc\s+name|machine\s+name|"
    r"logged\s+in\s+user|signed\s+in\s+user|who\s+am\s+i|"
    r"microphone|mic|audio\s+input|audio|speaker|camera|webcam|printer|"
    r"bluetooth|wifi|wi-fi|wireless|keyboard|mouse|touchpad|display|monitor|"
    r"dota\s*2|steam|"
    r"this\s+(pc|computer|machine|system))\b",
    re.I,
)

_LOCAL_GENERIC_ISSUE_PATTERN = re.compile(
    r"\b(printer|bluetooth|wifi|wi-fi|wireless|audio|speaker|microphone|mic|"
    r"camera|webcam|keyboard|mouse|touchpad|display|monitor|usb|chrome|edge|"
    r"firefox|browser|teams|outlook|word|excel)\b"
    r".{0,60}\b(not\s+working|not\s+responding|not\s+detected|not\s+connecting|"
    r"not\s+available|broken|failing|failed|issue|problem|error)\b",
    re.I,
)

_LOCAL_DIRECT_CHECK_PATTERN = re.compile(
    r"\b(is|are)\b.{1,80}\b(installed|available|present|connected|detected|running)\b"
    r"|\b(do i have|does my (system|pc|computer|machine) (have|has))\b"
    r"|\bwhat\b.{1,80}\b(available|present|connected|detected)\b"
    r"|\bcheck\s+(whether|if)\b",
    re.I,
)

_KEYWORD_RULES = [
    (
        r"\b(local\s+system\s+agent|local\s+agent|system\s+agent|workstation\s+agent)\b",
        "local_system_agent",
    ),
    (
        r"\b(chrome|edge|firefox|browser|teams|outlook|word|excel|app|application)\b.{0,50}\b(not\s+working|not\s+opening|not\s+responding|not\s+launching|won'?t\s+open|unable\s+to\s+open|crash(?:es|ing)?|broken|failing|failed)\b",
        "local_system_agent",
    ),
    (
        r"\b(disk\s+(space|usage|free)|free\s+space|c\s*drive|windows\s+version|os\s+version|top\s+process(es)?|running\s+process(es)?|services?|memory\s+usage|cpu\s+usage|workstation|this\s+(pc|computer|machine|system))\b",
        "local_system_agent",
    ),
    (
        r"\b(current\s+(time|date|user)|system\s+(time|date)|timezone|time\s+zone|host\s*name|hostname|computer\s+name|pc\s+name|machine\s+name|logged\s+in\s+user|signed\s+in\s+user|who\s+am\s+i)\b",
        "local_system_agent",
    ),
    (
        r"\b(windows update|update failure|update failed|windows patch|patching failed|0x[0-9a-f]{4,})\b",
        "windows_update_failure",
    ),
    (
        r"\b(slow|hang|hanging|freez(e|ing)|laggy|performance|sluggish|crawling|unresponsive|stutter(ing)?|takes?\s+forever)\b",
        "system_slow_diagnostics",
    ),
    (
        r"\b(new employee|employee onboarding|onboard.*(employee|user|hire)|new hire|new user|joiner|create.*ad account)\b",
        "new_employee_onboarding",
    ),
    (
        r"\b(full\s+name|work\s+email|department|dept|role|job\s+title)\b",
        "new_employee_onboarding",
    ),
    (r"\b(password|reset.*password|forgot.*password)\b", "password_reset"),
    (r"\b(vpn|remote access)\b", "vpn_access"),
    (
        r"\b(install (a|new) (software|app)|software install|software request)\b",
        "software_install",
    ),
    (r"\b(account.*locked|unlock.*account|locked out)\b", "account_unlock"),
    (r"\b(ticket status|status of (my|ticket)|incident status)\b", "ticket_status"),
    (r"\b(outage|application.*down|service.*down)\b", "application_outage"),
]


def classify_intent(message: str) -> str:
    if not message:
        return "unknown"

    text = _normalize_text(message)
    if _looks_like_explicit_outage(text):
        return "application_outage"
    if _looks_like_local_app_issue(text):
        return "local_system_agent"
    if _looks_like_local_generic_issue(text):
        return "local_system_agent"
    if _looks_like_local_system_query(text) or _looks_like_local_direct_check(text):
        return "local_system_agent"

    llm_result = _classify_with_llm(message)
    if llm_result and llm_result != "unknown":
        return llm_result

    for pattern, workflow_id in _KEYWORD_RULES:
        if re.search(pattern, text):
            return workflow_id
    return "unknown"


def _looks_like_local_app_issue(text: str) -> bool:
    return bool(_LOCAL_APP_ISSUE_PATTERN.search(text or ""))


def _looks_like_explicit_outage(text: str) -> bool:
    return bool(_EXPLICIT_OUTAGE_PATTERN.search(text or ""))


def _looks_like_local_system_query(text: str) -> bool:
    return bool(_LOCAL_SYSTEM_QUERY_PATTERN.search(text or ""))


def _looks_like_local_direct_check(text: str) -> bool:
    return bool(_LOCAL_DIRECT_CHECK_PATTERN.search(text or ""))


def _looks_like_local_generic_issue(text: str) -> bool:
    return bool(_LOCAL_GENERIC_ISSUE_PATTERN.search(text or ""))


def _normalize_text(message: str) -> str:
    text = (message or "").lower()
    replacements = {
        "michrophone": "microphone",
        "microfone": "microphone",
        "micophone": "microphone",
        "avaliable": "available",
        "availabe": "available",
        "avialable": "available",
        "dota2": "dota 2",
    }
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)
    return text


def _classify_with_llm(message: str) -> Optional[str]:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        prompt = INTENT_CLASSIFY_PROMPT.format(message=message)
        result = llm.invoke([HumanMessage(content=prompt)])
        text = (result.content or "").strip().lower()
        valid = {
            "local_system_agent",
            "system_slow_diagnostics",
            "new_employee_onboarding",
            "windows_update_failure",
            "password_reset",
            "vpn_access",
            "software_install",
            "account_unlock",
            "ticket_status",
            "application_outage",
            "unknown",
        }
        for token in re.split(r"[\s,;]+", text):
            if token in valid:
                return token
    except Exception:
        return None
    return None
