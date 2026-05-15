"""File-backed mock identity adapter.

This is the local stand-in for AD/Entra ID. It gives the onboarding workflow
real adapter behavior: lookup first, create only when absent, and persist the
mock user record across sessions.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional


class MockIdentityAdapter:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = (
            db_path
            or Path(__file__).resolve().parents[3] / "data" / "mock_identity_db.json"
        )
        self._lock = RLock()
        self._ensure_db()

    def get_by_email(self, email: str) -> Optional[Dict]:
        normalized = email.strip().lower()
        with self._lock:
            users = self._read()
            return users.get(normalized)

    def create_user(
        self, employee: Dict[str, str], groups: Optional[List[str]] = None
    ) -> Dict:
        email = employee["email"].strip().lower()
        username = email.split("@", 1)[0]
        user = {
            "email": email,
            "username": username,
            "full_name": employee["full_name"],
            "department": employee["department"],
            "role": employee["role"],
            "manager": employee.get("manager"),
            "groups": groups or [],
            "mfa_status": "not_enrolled",
            "welcome_email_sent": False,
            "status": "created",
            "directory": "Mock AD JSON DB",
        }
        with self._lock:
            users = self._read()
            if email in users:
                return users[email]
            users[email] = user
            self._write(users)
        return user

    def assign_groups(self, email: str, groups: List[str]) -> Dict:
        return self._update_user(
            email,
            lambda user: {
                **user,
                "groups": list(dict.fromkeys([*(user.get("groups") or []), *groups])),
            },
        )

    def enroll_mfa(self, email: str) -> Dict:
        return self._update_user(email, lambda user: {**user, "mfa_status": "enrolled"})

    def mark_welcome_email_sent(self, email: str) -> Dict:
        return self._update_user(
            email,
            lambda user: {**user, "welcome_email_sent": True},
        )

    def list_users(self) -> List[Dict]:
        with self._lock:
            return sorted(self._read().values(), key=lambda user: user["full_name"])

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._db_path.exists():
            self._db_path.write_text("{}", encoding="utf-8")

    def _read(self) -> Dict[str, Dict]:
        self._ensure_db()
        try:
            return json.loads(self._db_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write(self, users: Dict[str, Dict]) -> None:
        self._db_path.write_text(
            json.dumps(users, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _update_user(self, email: str, update_fn) -> Dict[str, Any]:
        normalized = email.strip().lower()
        with self._lock:
            users = self._read()
            if normalized not in users:
                raise ValueError(f"User {normalized} does not exist")
            users[normalized] = update_fn(users[normalized])
            self._write(users)
            return users[normalized]


mock_identity_adapter = MockIdentityAdapter()
