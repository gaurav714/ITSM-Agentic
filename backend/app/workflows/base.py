"""Base workflow contract — every workflow must implement `handle`."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from app.models.schemas import AgentMessageResponse


class BaseWorkflow(ABC):
    workflow_id: str = ""
    title: str = ""
    active: bool = True

    @abstractmethod
    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse: ...


class PlaceholderWorkflow(BaseWorkflow):
    """Stub used for not-yet-implemented workflows."""

    active = False

    def __init__(self, workflow_id: str, title: str) -> None:
        self.workflow_id = workflow_id
        self.title = title

    def handle(
        self, session: Dict[str, Any], user_message: str
    ) -> AgentMessageResponse:
        return AgentMessageResponse(
            message=f"The '{self.title}' workflow is coming soon. For now, only System Slow Diagnostics is supported.",
            workflow=self.workflow_id,
            state="coming_soon",
            requires_input=False,
        )
