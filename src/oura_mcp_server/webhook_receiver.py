"""In-process store for Oura webhook callback events.

The ``/webhook`` HTTP route (see ``server.py``) answers Oura's verification
challenge and records pushed events here. The buffer is in-memory only: it holds
the most recent ``MAX_EVENTS`` events and is cleared on process restart. Oura
event payloads carry only identifiers (event/data type, object id, user id);
the actual data is fetched from the API using the object id.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Any

MAX_EVENTS = 200

_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)


def verification_token() -> str | None:
    """The shared secret Oura echoes back in its verification GET, from env."""
    return os.environ.get("OURA_WEBHOOK_VERIFICATION_TOKEN") or None


def record_event(event: dict[str, Any]) -> None:
    _events.append(event)


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent events, newest first."""
    return list(_events)[-limit:][::-1]


def clear_events() -> None:
    _events.clear()
