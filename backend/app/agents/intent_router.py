"""Intent router — classifies a user message into a workflow id.

Uses an LLM when `OPENAI_API_KEY` is set, otherwise falls back to a keyword
heuristic that's sufficient for iteration 1 acceptance criteria.
"""

from __future__ import annotations

import re
from typing import Optional

from app.config import get_settings
from app.workflows.system_slow.prompts import INTENT_CLASSIFY_PROMPT

_KEYWORD_RULES = [
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

    llm_result = _classify_with_llm(message)
    if llm_result and llm_result != "unknown":
        return llm_result

    text = message.lower()
    for pattern, workflow_id in _KEYWORD_RULES:
        if re.search(pattern, text):
            return workflow_id
    return "unknown"


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
            "system_slow_diagnostics",
            "new_employee_onboarding",
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
