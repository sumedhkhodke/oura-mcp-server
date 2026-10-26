"""In-process store for Oura webhook callback events.

The ``/webhook`` HTTP route (see ``server.py``) answers Oura's verification
challenge and records pushed events here. The buffer is in-memory only: it holds
the most recent ``MAX_EVENTS`` events and is cleared on process restart. Oura
event payloads carry only identifiers (event/data type, object id, user id);
the actual data is fetched from the API using the object id.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import deque
from typing import Any, Literal

MAX_EVENTS = 200
SIGNATURE_MODES = ("log", "enforce", "off")

SignatureStatus = Literal["valid", "invalid", "missing", "unconfigured"]

_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)


def verification_token() -> str | None:
    """The shared secret Oura echoes back in its verification GET, from env."""
    return os.environ.get("OURA_WEBHOOK_VERIFICATION_TOKEN") or None


def signature_mode() -> str:
    """How POSTs are checked against ``x-oura-signature``, from ``OURA_WEBHOOK_SIGNATURE_MODE``.

    ``log`` (default) records every event and warns on a bad signature; ``enforce``
    rejects anything not validly signed; ``off`` skips the check. Unknown values
    fall back to ``log`` so a typo can never silently disable the warning.
    """
    mode = os.environ.get("OURA_WEBHOOK_SIGNATURE_MODE", "").strip().lower()
    return mode if mode in SIGNATURE_MODES else "log"


def verify_signature(
    body: bytes, event: Any, timestamp: str | None, signature: str | None, secret: str | None
) -> SignatureStatus:
    """Check Oura's webhook signature.

    Oura sends ``x-oura-signature`` = uppercase hex HMAC-SHA256 keyed with the
    OAuth client secret over ``x-oura-timestamp + JSON.stringify(body)``. The
    raw bytes are tried first; a compact re-serialization of the parsed body
    covers senders whose bytes differ from ``JSON.stringify`` only in whitespace.
    """
    if not secret:
        return "unconfigured"
    if not timestamp or not signature:
        return "missing"
    candidates = [body, json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()]
    for message in candidates:
        expected = hmac.new(secret.encode(), timestamp.encode() + message, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected.upper(), signature.strip().upper()):
            return "valid"
    return "invalid"


def record_event(event: dict[str, Any]) -> None:
    _events.append(event)


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent events, newest first."""
    return list(_events)[-limit:][::-1]


def clear_events() -> None:
    _events.clear()
