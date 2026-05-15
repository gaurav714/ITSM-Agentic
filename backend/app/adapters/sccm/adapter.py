"""Mock SCCM/MECM adapter."""

from typing import Dict, Optional

_MOCK_SCCM_DEVICES = {
    "DESKTOP-SCCM-42": {
        "client_health": "healthy",
        "os": "Windows 10",
        "cpu_pct": 65,
        "memory_pct": 78,
        "disk_free_gb": 45.0,
        "pending_updates": 7,
        "top_processes": ["sqlservr.exe", "node.exe", "code.exe"],
    }
}


class SccmAdapter:
    name = "sccm"

    def device_exists(self, device_name: str) -> bool:
        return device_name.upper() in _MOCK_SCCM_DEVICES

    def collect(self, device_name: str) -> Optional[Dict]:
        return _MOCK_SCCM_DEVICES.get(device_name.upper())


sccm_adapter = SccmAdapter()
