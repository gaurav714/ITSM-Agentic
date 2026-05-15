"""Browser diagnostics adapter — stores payloads pushed from the frontend."""

from threading import RLock
from typing import Dict, Optional


class BrowserAdapter:
    name = "browser_only"

    def __init__(self) -> None:
        self._lock = RLock()
        self._payloads: Dict[str, Dict] = {}

    def submit(self, session_id: str, payload: Dict) -> None:
        with self._lock:
            self._payloads[session_id] = payload

    def get(self, session_id: str) -> Optional[Dict]:
        with self._lock:
            return self._payloads.get(session_id)


browser_adapter = BrowserAdapter()
