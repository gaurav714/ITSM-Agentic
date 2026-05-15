"""In-memory session store. Replace with Redis/DB for production."""

from threading import RLock
from typing import Any, Dict, List, Optional


class SessionStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "workflow": None,
                    "state": "idle",
                    "device_name": None,
                    "diagnostic_id": None,
                    "diagnostic": None,
                    "messages": [],
                    "ticket_draft": None,
                    "ticket_id": None,
                }
            return self._sessions[session_id]

    def update(self, session_id: str, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            data = self.get(session_id)
            data.update(kwargs)
            return data

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self.get(session_id)["messages"].append({"role": role, "content": content})

    def messages(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            return list(self.get(session_id)["messages"])

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


session_store = SessionStore()
