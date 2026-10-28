"""The public guard must reject before callers make model requests."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from sera import public_demo
from sera.public_demo import DemoLimitError, public_demo_enabled, reserve_ai_request


@pytest.fixture(autouse=True)
def isolated_guard(monkeypatch):
    monkeypatch.setenv("SERA_PUBLIC_DEMO", "true")
    monkeypatch.delenv("SERA_PUBLIC_AI_SESSION_LIMIT", raising=False)
    monkeypatch.delenv("SERA_PUBLIC_AI_DAILY_LIMIT", raising=False)
    monkeypatch.setattr(public_demo, "_daily_day", None)
    monkeypatch.setattr(public_demo, "_daily_count", 0)
    clock = {"now": 100.0, "day": "2026-10-27"}
    monkeypatch.setattr(public_demo, "_clock", lambda: clock["now"])
    monkeypatch.setattr(public_demo, "_utc_day", lambda: clock["day"])
    return clock


@pytest.mark.parametrize("value", ["true", "1", "yes", " YES ", "True"])
def test_public_mode_enabled_only_explicitly(monkeypatch, value):
    monkeypatch.setenv("SERA_PUBLIC_DEMO", value)
    assert public_demo_enabled()


@pytest.mark.parametrize("value", ["", "false", "0", "no", "public"])
def test_local_mode_never_consumes_limits(monkeypatch, value):
    monkeypatch.setenv("SERA_PUBLIC_DEMO", value)
    assert not public_demo_enabled()
    state = {}
    for _ in range(200):
        reserve_ai_request(state)
    assert state == {}
    assert public_demo._daily_count == 0


def test_visitors_have_separate_session_allowances(isolated_guard):
    first, second = {}, {}
    reserve_ai_request(first)
    reserve_ai_request(second)
    with pytest.raises(DemoLimitError, match="wait 10 seconds"):
        reserve_ai_request(first)
    isolated_guard["now"] += 10
    reserve_ai_request(first)
    assert first[public_demo._SESSION_KEY][0] == 2
    assert second[public_demo._SESSION_KEY][0] == 1
    assert public_demo._daily_count == 3


def test_rejected_cooldown_does_not_consume_or_extend_allowance(isolated_guard):
    state = {}
    reserve_ai_request(state)
    before = dict(state)
    isolated_guard["now"] += 9.1
    with pytest.raises(DemoLimitError, match="wait 1 second"):
        reserve_ai_request(state)
    assert state == before
    assert public_demo._daily_count == 1
    isolated_guard["now"] += 0.9
    reserve_ai_request(state)
    assert public_demo._daily_count == 2


def test_session_limit_survives_conversation_reset(isolated_guard):
    state = {"chat": [], "history": []}
    for _ in range(10):
        reserve_ai_request(state)
        isolated_guard["now"] += 10
    state["chat"], state["history"] = [], []
    with pytest.raises(DemoLimitError, match="10 AI requests per visit"):
        reserve_ai_request(state)
    assert state[public_demo._SESSION_KEY][0] == 10
    assert public_demo._daily_count == 10


def test_shared_daily_limit_and_utc_rollover(isolated_guard, monkeypatch):
    monkeypatch.setenv("SERA_PUBLIC_AI_DAILY_LIMIT", "2")
    reserve_ai_request({})
    reserve_ai_request({})
    rejected = {}
    with pytest.raises(DemoLimitError, match="shared daily AI limit"):
        reserve_ai_request(rejected)
    assert rejected == {}
    assert public_demo._daily_count == 2
    isolated_guard["day"] = "2026-10-28"
    reserve_ai_request(rejected)
    assert rejected[public_demo._SESSION_KEY][0] == 1
    assert public_demo._daily_count == 1


def test_daily_rollover_does_not_reset_session_allowance(isolated_guard, monkeypatch):
    monkeypatch.setenv("SERA_PUBLIC_AI_SESSION_LIMIT", "1")
    state = {}
    reserve_ai_request(state)
    isolated_guard["day"] = "2026-10-28"
    isolated_guard["now"] += 20
    with pytest.raises(DemoLimitError, match="1 AI request per visit"):
        reserve_ai_request(state)


@pytest.mark.parametrize("value", ["0", "-1", "nonsense", "1.5", ""])
def test_invalid_configuration_uses_defaults(monkeypatch, value):
    monkeypatch.setenv("SERA_PUBLIC_AI_SESSION_LIMIT", value)
    monkeypatch.setenv("SERA_PUBLIC_AI_DAILY_LIMIT", value)
    assert public_demo._positive_limit("SERA_PUBLIC_AI_SESSION_LIMIT", 10, 100) == 10
    assert public_demo._positive_limit("SERA_PUBLIC_AI_DAILY_LIMIT", 100, 1000) == 100


def test_configuration_is_bounded_and_positive(monkeypatch, isolated_guard):
    monkeypatch.setenv("SERA_PUBLIC_AI_SESSION_LIMIT", "999999")
    monkeypatch.setenv("SERA_PUBLIC_AI_DAILY_LIMIT", "999999")
    assert public_demo._positive_limit("SERA_PUBLIC_AI_SESSION_LIMIT", 10, 100) == 100
    assert public_demo._positive_limit("SERA_PUBLIC_AI_DAILY_LIMIT", 100, 1000) == 1000
    monkeypatch.setenv("SERA_PUBLIC_AI_SESSION_LIMIT", "2")
    state = {}
    reserve_ai_request(state)
    isolated_guard["now"] += 10
    reserve_ai_request(state)
    isolated_guard["now"] += 10
    with pytest.raises(DemoLimitError, match="2 AI requests per visit"):
        reserve_ai_request(state)


def test_concurrent_visitors_cannot_overspend_daily_allowance(monkeypatch):
    monkeypatch.setenv("SERA_PUBLIC_AI_DAILY_LIMIT", "7")

    def reserve(_):
        try:
            reserve_ai_request({})
        except DemoLimitError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=16) as workers:
        accepted = list(workers.map(reserve, range(100)))
    assert sum(accepted) == 7
    assert public_demo._daily_count == 7


def test_concurrent_same_session_accepts_only_one_request():
    state = {}

    def reserve(_):
        try:
            reserve_ai_request(state)
        except DemoLimitError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=16) as workers:
        accepted = list(workers.map(reserve, range(50)))
    assert sum(accepted) == 1
    assert state[public_demo._SESSION_KEY][0] == 1
    assert public_demo._daily_count == 1


def test_session_write_failure_does_not_consume_shared_allowance():
    class ReadOnlyState(dict):
        def __setitem__(self, key, value):
            raise RuntimeError("Session unavailable")

    with pytest.raises(RuntimeError, match="Session unavailable"):
        reserve_ai_request(ReadOnlyState())
    assert public_demo._daily_day is None
    assert public_demo._daily_count == 0
