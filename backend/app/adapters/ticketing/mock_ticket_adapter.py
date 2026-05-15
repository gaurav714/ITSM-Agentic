"""Mock ticketing adapter — replace with ServiceNow/Jira in later iterations."""

import uuid
from threading import RLock
from typing import Dict, List


class MockTicketAdapter:
    def __init__(self) -> None:
        self._lock = RLock()
        self._tickets: Dict[str, Dict] = {}

    def create(self, draft: Dict) -> Dict:
        with self._lock:
            ticket_id = f"INC{uuid.uuid4().hex[:8].upper()}"
            ticket = {
                "ticket_id": ticket_id,
                "status": "Open",
                **draft,
            }
            self._tickets[ticket_id] = ticket
            return ticket

    def get(self, ticket_id: str) -> Dict | None:
        with self._lock:
            return self._tickets.get(ticket_id)

    def list(self) -> List[Dict]:
        with self._lock:
            return list(self._tickets.values())


mock_ticket_adapter = MockTicketAdapter()
