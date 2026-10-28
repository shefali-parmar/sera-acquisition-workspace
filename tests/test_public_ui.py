"""Public hosting isolation and request-limit integration through real UI actions."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from sera import ai
from sera.storage import SessionListStorage

APP = Path(__file__).parents[1] / "app.py"


@pytest.fixture
def public_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SERA_PUBLIC_DEMO", "true")
    monkeypatch.setenv("SERA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SERA_PUBLIC_AI_SESSION_LIMIT", "10")
    monkeypatch.setattr(ai, "configured", lambda: True)
    calls = []

    def unexpected_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("A limited or unsubmitted action reached the model")

    monkeypatch.setattr(ai, "investigate", unexpected_call)
    monkeypatch.setattr(ai, "extract_filters", unexpected_call)
    return tmp_path, calls


def start():
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    return app


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_public_visitors_never_load_shared_disk_lists(public_env):
    folder, _ = public_env
    path = folder / "saved_lists.json"
    path.write_text("existing private local data")
    first = start()
    _, storage, saved = first.session_state["runtime_records"]
    assert isinstance(storage, SessionListStorage)
    assert not saved.lists
    first.switch_page("screens/shortlists.py").run()
    first.text_input(key="new_list_name_first").set_value("Visitor one's list")
    click(first, "Create list")
    assert "Visitor one's list" in str(first.session_state["runtime_records"][2])
    second = start()
    assert not second.session_state["runtime_records"][2].lists
    assert path.read_text() == "existing private local data"
    assert any("private to this visit" in caption.value for caption in second.caption)


def test_limit_prevents_filter_extraction_and_preserves_description(public_env):
    _, calls = public_env
    app = start()
    app.session_state["_sera_public_ai_usage"] = (10, None)
    app.text_area(key="search_description").set_value("Dermatology in California").run()
    click(app, "Suggest editable filters")
    assert not calls
    assert app.session_state["description_draft"] == "Dermatology in California"
    assert any("10 AI requests" in item.value for item in app.info)


def test_starter_does_not_call_model_and_limit_preserves_chat_draft(public_env):
    _, calls = public_env
    app = start().switch_page("screens/ask_sera.py").run()
    app.session_state["_sera_public_ai_usage"] = (10, None)
    click(app, "Lease or buy?")
    assert not calls
    draft = app.text_area(key="assistant_question").value
    assert draft
    click(app, "Send")
    assert not calls
    assert app.text_area(key="assistant_question").value == draft
    assert not app.session_state["chat"]
    assert any("10 AI requests" in item.value for item in app.info)


def test_limit_prevents_detail_brief_request(public_env):
    _, calls = public_env
    app = AppTest.from_string(
        """
import streamlit as st
from app import run_analysis
from sera.models import Filters
st.session_state.filters = Filters()
st.session_state.goals = ""
st.session_state.analyses = {}
st.session_state._sera_public_ai_usage = (10, None)
run_analysis("SERA-001", "Review this practice", ["SERA-001"], ())
"""
    ).run()
    assert not app.exception
    assert not calls
    assert not app.session_state["analyses"]
    assert any("10 AI requests" in item.value for item in app.info)
