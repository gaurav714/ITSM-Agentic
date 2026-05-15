"""Mock Intune adapter. Replace with Microsoft Graph integration in iteration 2."""

from typing import Dict, Optional

# Mock device inventory for demo purposes.
_MOCK_INTUNE_DEVICES = {
    "LAPTOP-INTUNE-01": {
        "compliance_state": "compliant",
        "last_sync": "2026-05-09T18:00:00Z",
        "os": "Windows 11",
        "cpu_pct": 87,
        "memory_pct": 92,
        "disk_free_gb": 12.4,
        "top_processes": ["chrome.exe", "Teams.exe", "OUTLOOK.EXE"],
    }
}


class IntuneAdapter:
    name = "intune"

    def device_exists(self, device_name: str) -> bool:
        return device_name.upper() in _MOCK_INTUNE_DEVICES

    def collect(self, device_name: str) -> Optional[Dict]:
        return _MOCK_INTUNE_DEVICES.get(device_name.upper())


intune_adapter = IntuneAdapter()
