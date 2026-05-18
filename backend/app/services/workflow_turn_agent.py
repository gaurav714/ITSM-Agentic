"""Tool-constrained workflow turn decisions.

The helpers here let a workflow ask a LangGraph ReAct agent to choose the next
move from an allowlist. Workflows still own execution and guardrails.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.services.llm import llm_client


def choose_workflow_tool(
    *,
    agent_name: str,
    system_prompt: str,
    objective: Dict[str, Any],
    tool_options: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Return the first allowlisted tool selected by a ReAct agent, if available."""
    llm = llm_client()
    if llm is None:
        return None

    trace: List[Dict[str, Any]] = []
    tools = _build_choice_tools(tool_options, trace)
    try:
        agent = create_react_agent(
            llm,
            tools,
            messages_modifier=system_prompt,
        )
        agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            f"{agent_name} must choose exactly one tool for this turn.\n"
                            + json.dumps(objective, indent=2)
                        )
                    )
                ]
            }
        )
    except Exception:
        return None

    return trace[0] if trace else None


def agent_metadata(
    agent_name: str, tool_trace: Iterable[Dict[str, Any]], next_action: str | None
) -> Dict[str, Any]:
    return {
        "agentic": True,
        "agent_name": agent_name,
        "tool_trace": list(tool_trace),
        "next_action": next_action,
    }


def _build_choice_tools(
    tool_options: Dict[str, str], trace: List[Dict[str, Any]]
):
    built_tools = []

    for name, description in tool_options.items():

        def _choose(name=name, description=description) -> Dict[str, Any]:
            event = {"tool": name, "status": "selected", "description": description}
            trace.append(event)
            return event

        _choose.__name__ = name
        _choose.__doc__ = description
        built_tools.append(tool(_choose))

    return built_tools
