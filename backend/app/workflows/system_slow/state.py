"""LangGraph state schema for the System Slow workflow."""

from typing import Any, Dict, Optional, TypedDict


class SystemSlowState(TypedDict, total=False):
    session_id: str
    user_message: str
    device_name: Optional[str]
    diagnostic_id: Optional[str]
    diagnostic: Optional[Dict[str, Any]]
    summary: Optional[str]
    next_state: str
    assistant_message: str
