"""Bound public demo AI actions without identifying or persisting visitors.

These are request limits, not a billing ceiling: one UI action may use several
bounded model calls. Session allowances reset when the browser session ends;
the shared UTC-day allowance resets when this server process restarts. Multiple
server processes each have their own allowance. Local use is unaffected.
"""

import math
import os
import threading
import time
from collections.abc import MutableMapping
from datetime import datetime, timezone
from typing import Any

_SESSION_KEY = "_sera_public_ai_usage"
_COOLDOWN_SECONDS = 10
_lock = threading.RLock()
_daily_day: str | None = None
_daily_count = 0


class DemoLimitError(ValueError):
    """An AI action was rejected before it could call a model."""


def public_demo_enabled() -> bool:
    return os.getenv("SERA_PUBLIC_DEMO", "").strip().lower() in {"true", "1", "yes"}


def _positive_limit(name: str, default: int, maximum: int) -> int:
    """Ignore malformed settings and cap valid positive settings."""
    try:
        value = int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default
    return min(value, maximum) if value > 0 else default


def _clock() -> float:
    return time.monotonic()


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def reserve_ai_request(state: MutableMapping[str, Any]) -> None:
    """Atomically reserve one UI action, or raise without consuming allowance.

    Call immediately before every model-backed UI action. Keep the private
    session key when resetting conversations so starting a new conversation
    cannot reset the allowance. Accepted actions count even if the model fails.
    Optional session/daily limits default to 10/100 and are capped at 100/1000.
    """
    if not public_demo_enabled():
        return

    session_limit = _positive_limit("SERA_PUBLIC_AI_SESSION_LIMIT", 10, 100)
    daily_limit = _positive_limit("SERA_PUBLIC_AI_DAILY_LIMIT", 100, 1000)
    global _daily_day, _daily_count
    with _lock:
        now = _clock()
        day = _utc_day()
        count, last_request = state.get(_SESSION_KEY, (0, None))
        day_count = _daily_count if day == _daily_day else 0
        if count >= session_limit:
            request_word = "request" if session_limit == 1 else "requests"
            raise DemoLimitError(
                f"This demo allows {session_limit} AI {request_word} per visit. "
                "You can still browse practices and export shortlists."
            )
        if last_request is not None and now - last_request < _COOLDOWN_SECONDS:
            wait = max(1, math.ceil(_COOLDOWN_SECONDS - (now - last_request)))
            time_word = "second" if wait == 1 else "seconds"
            raise DemoLimitError(f"Please wait {wait} {time_word} before asking SERA again.")
        if day_count >= daily_limit:
            raise DemoLimitError(
                "SERA has reached its shared daily AI limit. "
                "Browsing and shortlists remain available."
            )

        # A single session write completes before shared allowance is consumed.
        state[_SESSION_KEY] = (count + 1, now)
        _daily_day, _daily_count = day, day_count + 1
