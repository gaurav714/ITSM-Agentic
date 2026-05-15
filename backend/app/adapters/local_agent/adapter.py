"""Mock local agent adapter (queue-based architecture in production)."""

from typing import Dict, Optional

_MOCK_AGENT_DEVICES = {
    "WS-AGENT-7": {
        "cpu_pct": 95,
        "memory_pct": 88,
        "disk_free_gb": 5.2,
        "top_processes": ["python.exe", "chrome.exe", "Docker Desktop.exe"],
        "recent_event_errors": 4,
    }
}


class LocalAgentAdapter:
    name = "custom_agent"

    def device_registered(self, device_name: str) -> bool:
        return device_name.upper() in _MOCK_AGENT_DEVICES

    def collect(self, device_name: str) -> Optional[Dict]:
        return _MOCK_AGENT_DEVICES.get(device_name.upper())


local_agent_adapter = LocalAgentAdapter()
