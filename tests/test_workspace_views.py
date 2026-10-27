"""Exercise workspace views in isolation; no provider or model calls are made."""

import json

import pytest
from streamlit.testing.v1 import AppTest

from sera.catalog import load_practices
from sera.models import Filters
from sera.storage import ListStorage

HARNESS = """
import json
import streamlit as st
from sera.catalog import load_practices
from sera.models import Filters
from sera.storage import ListStorage
from sera.workspace_views import WorkspaceCallbacks, render_shortlists, render_assistant

for key, value in {"filters": Filters(), "history": [], "chat": [], "analyses": {}, "goals": "Original priorities", "test_calls": [], "test_ai": True}.items():
    if key not in st.session_state:
        st.session_state[key] = value
records = {p.id: p for p in load_practices()}
storage = ListStorage()
saved = storage.load()
section = st.sidebar.radio("Workspace", ["Saved lists", "Acquisition assistant", "Explore practices"], key="workspace")

def card(practice, storage, saved, *, key_prefix, comparison_selected=None, on_compare_change=None):
    st.markdown("CANDIDATE " + practice.name)
    if comparison_selected is not None:
        key = key_prefix + "_select_" + practice.id
        def changed():
            st.session_state[key] = on_compare_change(practice.id, st.session_state[key])
        st.checkbox("Select " + practice.name, value=comparison_selected, key=key, on_change=changed)

def goals():
    return st.session_state.goals + "\\nSearch preferences: \\nUnverifiable requirements: \\nApplied filters: " + json.dumps(st.session_state.filters.model_dump())

def action(operation):
    try:
        operation()
        return True
    except (ValueError, OSError) as error:
        st.error(str(error))
        return False

def investigate(question, context, history, required_ids=None):
    from sera.ai import investigation_ids
    st.session_state.test_calls.append((question, context, required_ids))
    resolved_calls = st.session_state.get("test_resolved_calls", [])
    st.session_state.test_resolved_calls = resolved_calls + [investigation_ids(question, history, required_ids)]
    if st.session_state.get("test_fail", False):
        raise RuntimeError("Scripted failure")
    return {"answer": "Scripted answer", "history": ["bounded scripted history"]}

def analysis(key, question, ids, signature):
    st.session_state.test_analysis = (key, question, ids, signature)

callbacks = WorkspaceCallbacks(card=card, effective_goals=goals,
    criteria_summary=lambda filters: "Under " + str(filters.max_price) if not filters.max_price_inclusive else "Up to " + str(filters.max_price),
    storage_action=action, run_analysis=analysis, show_analysis=lambda key, signature: None,
    show_sources=lambda result: None, show_assessment_notice=lambda result: None,
    buyer_answer_markdown=lambda answer: answer, ai_configured=lambda: st.session_state.test_ai,
    investigate=investigate)
if section == "Saved lists":
    render_shortlists(records, storage, saved, callbacks)
elif section == "Acquisition assistant":
    render_assistant(records, callbacks, saved=saved)
else:
    st.write("Explore screen")
"""


def _element(items, label):
    return next(item for item in items if item.label == label)


def _click(app, label):
    return _element(app.button, label).click().run()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setenv("SERA_DATA_DIR", str(tmp_path / "lists"))
    file = tmp_path / "workspace_harness.py"
    file.write_text(HARNESS)
    return file


def _start(harness):
    app = AppTest.from_file(str(harness), default_timeout=15).run()
    assert not app.exception
    return app


def _seed(*ids):
    storage = ListStorage()
    first = storage.create("Primary", practice_ids=list(ids))
    return storage, first


def _select(app, pid, selected=True):
    name = next(practice.name for practice in load_practices() if practice.id == pid)
    _element(app.checkbox, "Select " + name).set_value(selected).run()
    assert not app.exception
    return app


def test_shortlists_start_unselected_and_require_explicit_comparison(harness):
    _seed("SERA-001", "SERA-002", "SERA-003", "SERA-004")
    app = _start(harness)
    assert not app.checkbox[0].value
    assert _element(app.button, "Compare selected").disabled
    assert not any("sera-comparison" in item.value for item in app.markdown)
    _select(app, "SERA-001")
    assert _element(app.button, "Compare selected").disabled
    _select(app, "SERA-002")
    assert not _element(app.button, "Compare selected").disabled
    assert not any("sera-comparison" in item.value for item in app.markdown)
    _click(app, "Compare selected")
    assert any("sera-comparison" in item.value for item in app.markdown)
    _click(app, "Generate AI comparison")
    assert app.session_state["test_analysis"][2] == ["SERA-001", "SERA-002"]
    _select(app, "SERA-003")
    _select(app, "SERA-004")
    assert not _element(app.checkbox, "Select " + load_practices()[3].name).value
    assert any("up to three" in warning.value for warning in app.warning)
    assert (
        len(app.session_state["shortlist_comparison_selection"][app.session_state["selected_list"]])
        == 3
    )
    _click(app, "Clear selection")
    assert not any(checkbox.value for checkbox in app.checkbox)


def test_selection_survives_navigation_and_is_per_list(harness):
    storage, first = _seed("SERA-001", "SERA-002")
    second = storage.create("Secondary", practice_ids=["SERA-003", "SERA-004"])
    app = _start(harness)
    _select(app, "SERA-001")
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    app.sidebar.radio[0].set_value("Saved lists").run()
    assert app.checkbox[0].value
    app.selectbox[0].set_value(second).run()
    assert not any(item.value for item in app.checkbox)
    _select(app, "SERA-003")
    app.selectbox[0].set_value(first).run()
    assert app.session_state["shortlist_comparison_selection"][first] == ["SERA-001"]
    assert app.session_state["shortlist_comparison_selection"][second] == ["SERA-003"]
    storage.update(first, practice_ids=["SERA-002"])
    app.run()
    assert app.session_state["shortlist_comparison_selection"][first] == []
    assert not any(item.value for item in app.checkbox)


def test_edit_membership_retains_unavailable_ids_and_exports_whole_list(harness):
    storage, first = _seed("SERA-001", "SERA-002")
    saved = storage.load()
    saved.lists[0].practice_ids.append("SERA-999")
    storage.path.write_text(saved.model_dump_json())  # Simulate a historical catalog entry.
    app = _start(harness)
    assert any("unavailable" in warning.value for warning in app.warning)
    _element(app.multiselect, "Practices in this list · remove or add candidates").set_value(
        ["SERA-001"]
    )
    _click(app, "Save list changes")
    assert storage.load().lists[0].practice_ids == ["SERA-001", "SERA-999"]
    assert len(app.get("download_button")) == 2
    assert app.session_state["shortlist_comparison_selection"][first] == []


def test_delete_requires_second_action_and_detects_concurrent_change(harness):
    storage, first = _seed("SERA-001")
    app = _start(harness)
    assert not any(button.label == "Delete permanently" for button in app.button)
    _click(app, "Delete list")
    assert storage.load().lists
    assert any(button.label == "Delete permanently" for button in app.button)
    storage.update(first, name="Changed externally")
    _click(app, "Delete permanently")
    assert storage.load().lists[0].name == "Changed externally"
    assert any("changed in another tab" in error.value for error in app.error)
    assert not app.exception


def test_list_creation_selects_new_list_and_rename_uses_snapshot(harness):
    _seed("SERA-001")
    app = _start(harness)
    _element(app.text_input, "New list name").set_value("Another list")
    _click(app, "Create list")
    storage = ListStorage()
    item = next(item for item in storage.load().lists if item.name == "Another list")
    assert app.session_state["selected_list"] == item.id
    _element(app.text_input, "List name").set_value("Renamed list")
    _click(app, "Save name")
    assert next(x for x in storage.load().lists if x.id == item.id).name == "Renamed list"
    assert not app.exception


def test_empty_shortlist_has_direct_explore_action(harness):
    app = _start(harness)
    _click(app, "Explore practices")
    assert app.sidebar.radio[0].value == "Explore practices"
    assert app.session_state["requested_page"] == "screens/explore.py"
    assert not app.exception


def test_assistant_starters_populate_without_request_and_new_only_after_turn(harness):
    app = _start(harness)
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    assert not any(button.label == "Start a new conversation" for button in app.button)
    assert not any(item.label == "Deal context" for item in app.expander)
    _click(app, "Evaluate a practice")
    assert "acquisition review" in app.text_area[0].value
    assert app.session_state["test_calls"] == []
    _click(app, "Send")
    assert len(app.session_state["test_calls"]) == 1
    assert len(app.chat_message) == 2
    assert any(button.label == "Start a new conversation" for button in app.button)
    _click(app, "Start a new conversation")
    assert not app.chat_message
    assert app.session_state["chat"] == []
    assert not app.exception


def test_assistant_names_snapshot_candidates_and_preserves_failed_question(harness):
    app = _start(harness)
    snapshot = (
        "Original priorities\nSearch preferences: \nUnverifiable requirements: \nApplied filters: "
        + json.dumps(Filters(max_price=1500000, max_price_inclusive=False).model_dump())
    )
    app.session_state["chat_context"] = snapshot
    app.session_state["chat_required_ids"] = ["SERA-001", "SERA-002"]
    app.session_state["goals"] = "Changed priorities"
    app.session_state["test_fail"] = True
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    assert any(load_practices()[0].name in item.value for item in app.markdown)
    assert app.session_state["chat_context"] == snapshot
    assert any("keeps the buyer goals" in item.value for item in app.info)
    _click(app, "Assess a property")
    question = app.text_area[0].value
    _click(app, "Send")
    assert app.text_area[0].value == question
    assert app.session_state["chat"] == []
    assert app.session_state["chat_context"] == snapshot
    assert app.session_state["test_calls"][-1][2] == ["SERA-001", "SERA-002"]
    assert any("question and conversation are preserved" in item.value for item in app.error)
    assert not app.exception


def test_delete_cancel_and_success_are_explicit(harness):
    storage, first = _seed("SERA-001")
    app = _start(harness)
    _click(app, "Delete list")
    _click(app, "Cancel")
    assert storage.load().lists[0].id == first
    assert "shortlist_delete_snapshot" not in app.session_state
    _click(app, "Delete list")
    _click(app, "Delete permanently")
    assert storage.load().lists == []
    assert "shortlist_delete_snapshot" not in app.session_state
    assert not app.exception


def test_export_snapshot_uses_entire_list_instead_of_comparison_subset(harness, monkeypatch):
    import sera.workspace_views as views

    _seed("SERA-001", "SERA-002", "SERA-003")
    exports = []
    original = views.build_list_export

    def capture_export(*args, **kwargs):
        result = original(*args, **kwargs)
        exports.append(result)
        return result

    monkeypatch.setattr(views, "build_list_export", capture_export)
    app = _start(harness)
    _select(app, "SERA-001")
    _select(app, "SERA-002")
    _click(app, "Compare selected")
    assert exports[-1]["list"]["practice_ids"] == ["SERA-001", "SERA-002", "SERA-003"]
    assert len(exports[-1]["practices"]) == 3
    assert len(app.get("download_button")) == 2


def test_unavailable_assistant_scope_is_explicit_and_cannot_submit(harness):
    app = _start(harness)
    app.session_state["chat_required_ids"] = ["SERA-999"]
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    assert _element(app.button, "Send").disabled
    assert any("no longer available" in item.value for item in app.warning)
    assert app.session_state["test_calls"] == []
    assert not app.exception


def test_active_list_survives_hidden_widget_cleanup(harness):
    storage, _ = _seed("SERA-001")
    second = storage.create("Secondary", practice_ids=["SERA-002"])
    app = _start(harness)
    selector = _element(app.selectbox, "Choose list")
    assert selector.key != "selected_list"
    selector.set_value(second).run()
    assert app.session_state["selected_list"] == second
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    app.run()  # Exercise cleanup while the list selector is not rendered.
    assert app.session_state["selected_list"] == second
    app.sidebar.radio[0].set_value("Saved lists").run()
    assert _element(app.selectbox, "Choose list").value == second
    assert not app.exception


def _set_assessment_scope(app):
    snapshot = (
        "Original snapshot priorities\nSearch preferences: \nUnverifiable requirements: \nApplied filters: "
        + json.dumps(Filters(max_price=1500000).model_dump())
    )
    app.session_state["chat_context"] = snapshot
    app.session_state["chat_required_ids"] = ["SERA-001", "SERA-025"]
    app.session_state["chat"] = [
        {"role": "assistant", "content": "Original two-candidate assessment"}
    ]
    app.session_state["continuing_assessment"] = True
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    return snapshot


def test_explicit_candidate_change_updates_scope_and_next_pronoun_followup(harness):
    app = _start(harness)
    snapshot = _set_assessment_scope(app)
    app.text_area[0].set_value("Investigate SERA-007")
    _click(app, "Send")
    assert app.session_state["chat_required_ids"] == ["SERA-007"]
    assert app.session_state["test_resolved_calls"][-1] == ["SERA-007"]
    scope = [item.value for item in app.markdown if item.value.startswith("**")]
    records = {practice.id: practice for practice in load_practices()}
    assert records["SERA-007"].name in scope[0]
    assert records["SERA-001"].name not in scope[0]
    app.text_area[0].set_value("What is its price?")
    _click(app, "Send")
    assert app.session_state["test_calls"][-1][2] == ["SERA-007"]
    assert app.session_state["test_resolved_calls"][-1] == ["SERA-007"]
    assert app.session_state["chat_context"] == snapshot
    assert not app.exception


def test_fresh_discovery_clears_previous_assessment_candidate_scope(harness):
    app = _start(harness)
    snapshot = _set_assessment_scope(app)
    app.text_area[0].set_value("Find family medicine practices in Texas")
    _click(app, "Send")
    assert app.session_state["chat_required_ids"] == []
    assert app.session_state["test_resolved_calls"][-1] == []
    assert not any("Riverbend Dermatology" in item.value for item in app.markdown)
    assert not any(item.value.startswith("Practices:") for item in app.markdown)
    app.text_area[0].set_value("What evidence is missing?")
    _click(app, "Send")
    assert app.session_state["test_calls"][-1][2] == []
    assert app.session_state["chat_context"] == snapshot
    assert not app.exception


def test_scope_change_is_not_committed_on_failure_or_resolved_twice_for_ordinals(harness):
    app = _start(harness)
    snapshot = _set_assessment_scope(app)
    app.session_state["test_fail"] = True
    app.text_area[0].set_value("Investigate SERA-007")
    _click(app, "Send")
    assert app.session_state["chat_required_ids"] == ["SERA-001", "SERA-025"]
    assert app.session_state["chat_context"] == snapshot
    app.session_state["test_fail"] = False
    app.text_area[0].set_value("What is the second practice's price?")
    _click(app, "Send")
    assert app.session_state["test_resolved_calls"][-1] == ["SERA-025"]
    assert app.session_state["chat_required_ids"] == ["SERA-025"]
    assert not app.exception


def _choose_targets(app, ids):
    _element(app.multiselect, "Practices").set_value(ids)
    _click(app, "Use selected practices")
    assert not app.exception


def test_ma_targets_and_tasks_are_explicit_and_do_not_mutate_search_or_lists(harness):
    storage, first = _seed("SERA-001", "SERA-025", "SERA-007", "SERA-002")
    app = _start(harness)
    original_store = storage.path.read_text()
    app.session_state["filter_draft"] = Filters(states=["CA"])
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    assert not any(button.label == "Review a target" for button in app.button)
    assert not _element(app.button, "Lease or buy?").disabled
    _element(app.selectbox, "Choose from").set_value(first).run()
    _element(app.multiselect, "Practices").set_value(["SERA-001", "SERA-025"])
    assert "chat_required_ids" not in app.session_state
    assert app.session_state["test_calls"] == []
    _click(app, "Use selected practices")
    assert app.session_state["chat_required_ids"] == ["SERA-001", "SERA-025"]
    assert not _element(app.button, "Review a target").disabled
    for label in (
        "Review a target",
        "Lease or buy?",
        "Assess a property",
    ):
        _click(app, label)
        assert all(
            name in app.text_area[0].value
            for name in (load_practices()[0].name, load_practices()[24].name)
        )
        assert app.session_state["test_calls"] == []
    assert app.session_state["filters"] == Filters()
    assert app.session_state["filter_draft"] == Filters(states=["CA"])
    assert app.session_state["goals"] == "Original priorities"
    assert storage.path.read_text() == original_store
    _click(app, "Send")
    assert len(app.session_state["test_calls"]) == 1
    assert app.session_state["test_resolved_calls"][-1] == ["SERA-001", "SERA-025"]
    assert not any(button.label == "Use selected practices" for button in app.button)
    assert any(button.key == "export_deal_notes" for button in app.get("download_button"))
    _click(app, "Start a new conversation")
    assert "chat_required_ids" not in app.session_state
    assert _element(app.multiselect, "Practices").value == []
    assert storage.path.read_text() == original_store


def test_target_change_invalidates_generated_request_but_preserves_edited_draft(harness):
    app = _start(harness)
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    _choose_targets(app, ["SERA-001"])
    _click(app, "Review a target")
    _choose_targets(app, ["SERA-007"])
    assert app.text_area[0].value == ""
    assert app.session_state["chat_required_ids"] == ["SERA-007"]
    _click(app, "Review a target")
    edited = app.text_area[0].value + " Focus on staffing."
    app.text_area[0].set_value(edited).run()
    _choose_targets(app, ["SERA-025"])
    assert app.text_area[0].value == edited
    assert any("Check any practice names" in item.value for item in app.info)
    assert app.session_state["test_calls"] == []
    assert not app.exception


def test_target_picker_excludes_unavailable_shortlist_records_without_changing_storage(harness):
    storage, first = _seed("SERA-001")
    saved = storage.load()
    saved.lists[0].practice_ids.append("SERA-999")
    storage.path.write_text(saved.model_dump_json())
    before = storage.path.read_text()
    app = _start(harness)
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    _element(app.selectbox, "Choose from").set_value(first).run()
    assert _element(app.multiselect, "Practices").options == [
        "Riverbend Dermatology · Sacramento, CA"
    ]
    _choose_targets(app, ["SERA-001"])
    assert storage.path.read_text() == before
    assert app.session_state["test_calls"] == []
    app.sidebar.radio[0].set_value("Saved lists").run()
    app.run()
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    assert app.session_state["chat_required_ids"] == ["SERA-001"]
    assert not app.exception


def test_deal_context_is_removed_without_losing_snapshot_settings(harness):
    app = _start(harness)
    snapshot = _set_assessment_scope(app)
    app.session_state["goals"] = "New goals"
    app.run()
    assert not any(item.label == "Deal context" for item in app.expander)
    assert app.session_state["chat_context"] == snapshot
    assert not any("CONVERSATION CONTEXT" in item.value for item in app.markdown)
    assert not app.exception


def test_removed_context_still_supplies_preferences_and_unverifiable_requirements(harness):
    app = _start(harness)
    app.session_state["chat_context"] = (
        "Transition support\nSearch preferences: long owner tenure\n"
        "Unverifiable requirements: clean legal history\nApplied filters: "
        + Filters().model_dump_json()
    )
    app.sidebar.radio[0].set_value("Acquisition assistant").run()
    assert not any(item.label == "Deal context" for item in app.expander)
    assert app.session_state["test_calls"] == []
    _click(app, "Lease or buy?")
    _click(app, "Send")
    supplied = app.session_state["test_calls"][-1][1]
    assert "Search preferences: long owner tenure" in supplied
    assert "Unverifiable requirements: clean legal history" in supplied
