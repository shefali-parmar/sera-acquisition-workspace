"""User-facing regression flows; scripted AI never calls a provider."""

from html import escape
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from streamlit.testing.v1 import AppTest

from sera import ai
from sera.catalog import load_practices, search
from sera.models import Filters, SearchSuggestion
from sera.storage import ListStorage

APP = Path(__file__).parents[1] / "app.py"


def element(items, label):
    return next(item for item in items if item.label == label)


def click(app, label):
    return element(app.button, label).click().run()


def workspace(app, name):
    paths = {
        "Explore practices": "screens/explore.py",
        "Saved lists": "screens/shortlists.py",
        "Acquisition assistant": "screens/ask_sera.py",
    }
    return app.switch_page(paths[name]).run()


def visible_practice_ids(app):
    return [
        button.key.removeprefix("details_")
        for button in app.button
        if button.label == "View practice"
    ]


def select_comparison(app, ids):
    for pid in ids:
        widget = next(
            item
            for item in app.checkbox
            if item.label == "Select for comparison" and item.key.endswith(pid)
        )
        widget.check().run()
    click(app, "Compare selected")
    return app


def comparison_markup(app):
    return next(
        item.value for item in app.markdown if '<table class="sera-comparison"' in item.value
    )


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ai, "configured", lambda: False)
    return tmp_path


def start():
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    return app


def test_manual_filter_drafts_apply_navigation_and_reset(app_env):
    app = start()
    original = app.session_state["filters"]
    click(app, "Set filters manually")
    element(app.multiselect, "States · all 50 available").set_value(["AK"]).run()
    assert app.session_state["filters"] == original
    assert any("unapplied" in caption.value for caption in app.caption)
    workspace(app, "Saved lists")
    workspace(app, "Explore practices")
    assert element(app.multiselect, "States · all 50 available").value == ["AK"]
    click(app, "Apply filters")
    assert app.session_state["filters"].states == ["AK"]
    assert any("No fictional records" in info.value for info in app.info)
    workspace(app, "Saved lists")
    workspace(app, "Explore practices")
    assert not app.multiselect
    click(app, "Edit filters")
    assert element(app.multiselect, "States · all 50 available").value == ["AK"]
    click(app, "Reset all filters")
    assert app.session_state["filters"] == Filters()
    assert element(app.multiselect, "States · all 50 available").value == []
    assert not app.exception


def test_suggestion_approval_and_manual_edits_survive_navigation(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai,
        "extract_filters",
        lambda _: SearchSuggestion(
            filters=Filters(states=["CA"], max_price=1500000, max_price_inclusive=False),
            preferences=["Owner transition support"],
            unverifiable=["Verified profit"],
        ),
    )
    app = start()
    element(app.text_area, "Describe your ideal practice").set_value("California under 1.5m").run()
    click(app, "Suggest editable filters")
    assert not visible_practice_ids(app)
    assert app.session_state["filters"].states == []
    assert "search_preferences" not in app.session_state
    assert not element(app.checkbox, "Include practices exactly at the price cap").value
    element(app.text_input, "City · exact match, no radius").set_value("Sacramento").run()
    click(app, "Apply filters")
    assert app.session_state["filters"].city == "Sacramento"
    assert not app.multiselect
    assert visible_practice_ids(app)
    assert app.session_state["search_preferences"] == ["Owner transition support"]
    assert not app.session_state["filters"].max_price_inclusive
    assert any("Verified profit" in warning.value for warning in app.warning)
    assert not any("not applied yet" in value.value for value in app.success)
    workspace(app, "Saved lists")
    workspace(app, "Explore practices")
    assert not app.multiselect
    click(app, "Edit filters")
    assert element(app.text_input, "City · exact match, no radius").value == "Sacramento"
    assert any(item.value == "California under 1.5m" for item in app.markdown)
    click(app, "Revise request")
    assert element(app.text_area, "Describe your ideal practice").value == "California under 1.5m"
    assert not app.exception


def test_discard_suggestion_keeps_applied_context(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai,
        "extract_filters",
        lambda _: SearchSuggestion(
            filters=Filters(states=["CA"]),
            preferences=["Unapplied draft preference"],
        ),
    )
    app = start()
    element(app.text_area, "Describe your ideal practice").set_value("California").run()
    click(app, "Suggest editable filters")
    click(app, "Discard unapplied changes")
    assert app.session_state["filters"].states == []
    assert app.session_state["filter_draft"].states == []
    assert "search_preferences" not in app.session_state
    assert not app.multiselect
    assert visible_practice_ids(app)
    assert not app.exception


def test_corrupt_lists_preserved_and_browsing_keeps_working(app_env):
    path = app_env / "saved_lists.json"
    path.write_text("broken saved content")
    app = start()
    assert any("preserved" in error.value for error in app.error)
    assert any(button.label == "View practice" for button in app.button)
    workspace(app, "Saved lists")
    assert any("temporarily unavailable" in value.value for value in app.info)
    assert not any(button.label == "Create list" for button in app.button)
    workspace(app, "Acquisition assistant")
    assert element(app.button, "Send").disabled
    assert path.read_text() == "broken saved content"
    assert not app.exception


def test_failed_write_preserves_list_input_and_no_success(app_env, monkeypatch):
    def fail(self, name):
        raise OSError("Read-only disk")

    monkeypatch.setattr(ListStorage, "create", fail)
    app = start()
    workspace(app, "Saved lists")
    element(app.text_input, "New list name").set_value("California candidates")
    click(app, "Create list")
    assert element(app.text_input, "New list name").value == "California candidates"
    assert any("could not be saved" in error.value for error in app.error)
    assert not app.success
    assert not (app_env / "saved_lists.json").exists()
    assert not app.exception


def test_named_list_edit_compare_export_and_delete(app_env):
    app = start()
    workspace(app, "Saved lists")
    element(app.text_input, "New list name").set_value("West coast")
    click(app, "Create list")
    element(app.multiselect, "Practices in this list · remove or add candidates").set_value(
        ["SERA-001", "SERA-002", "SERA-003", "SERA-004"]
    )
    click(app, "Save list changes")
    assert not any(item.value for item in app.checkbox if item.label == "Select for comparison")
    assert not any('<table class="sera-comparison"' in item.value for item in app.markdown)
    select_comparison(app, ["SERA-001", "SERA-002", "SERA-003"])
    table = comparison_markup(app)
    assert table.count('<th scope="col">') == 4
    assert table.count('<th scope="row">') == 11
    records = {practice.id: practice for practice in load_practices()}
    for pid in ["SERA-001", "SERA-002", "SERA-003"]:
        assert f"<span>{escape(records[pid].name)}</span>" in table
    assert "SERA-001" not in table
    assert "white-space:normal" in table
    assert len(app.get("download_button")) == 2
    assert len(ListStorage().load().lists[0].practice_ids) == 4
    element(app.text_input, "List name").set_value("Reviewed west coast")
    click(app, "Save name")
    assert ListStorage().load().lists[0].name == "Reviewed west coast"
    click(app, "Delete list")
    assert element(app.button, "Delete permanently")
    assert ListStorage().load().lists  # no deletion until explicit confirmation
    assert not app.exception


def test_list_editor_refreshes_after_external_membership_update(app_env):
    storage = ListStorage()
    list_id = storage.create("Initial")
    storage.update(list_id, practice_ids=["SERA-001"])
    app = start()
    workspace(app, "Saved lists")
    storage.set_memberships("SERA-002", [list_id])
    app.run()
    member = element(app.multiselect, "Practices in this list · remove or add candidates")
    assert member.value == ["SERA-001", "SERA-002"]
    click(app, "Save list changes")
    assert storage.load().lists[0].practice_ids == ["SERA-001", "SERA-002"]
    assert not app.exception


def test_assessment_followup_keeps_snapshot_goals_and_selected_ids(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    calls = []

    def investigate(question, goals, history=None, required_ids=None):
        calls.append((question, goals, required_ids))
        return dict(
            answer="Scripted evidence assessment",
            calls=[],
            sources=[],
            history=[
                HumanMessage(
                    content=f"Current buyer goals: {goals}\nRequest: {question}\nRequired practice IDs to retrieve: {required_ids}"
                ),
                AIMessage(content="Scripted evidence assessment"),
            ],
        )

    monkeypatch.setattr(ai, "investigate", investigate)
    storage = ListStorage()
    list_id = storage.create("Compare")
    storage.update(list_id, practice_ids=["SERA-001", "SERA-002"])
    app = start()
    element(app.text_area, "Acquisition priorities (optional)").set_value(
        "Original buyer goals"
    ).run()
    workspace(app, "Saved lists")
    select_comparison(app, ["SERA-001", "SERA-002"])
    click(app, "Generate AI comparison")
    snapshot = calls[-1][1]
    element(app.text_area, "Acquisition priorities (optional)").set_value(
        "Changed buyer goals"
    ).run()
    assert any("out of date" in warning.value for warning in app.warning)
    click(app, "Ask a follow-up about this assessment")
    workspace(
        app, "Acquisition assistant"
    )  # AppTest does not consume frontend navigation messages.
    assert app.session_state["workspace"] == "Acquisition assistant"
    assert any("keeps the buyer goals" in info.value for info in app.info)
    element(app.text_area, "Ask SERA").set_value("Which has more missing information?")
    click(app, "Send")
    assert calls[-1][1] == snapshot
    assert calls[-1][2] == ["SERA-001", "SERA-002"]
    assert len(app.chat_message) == 3
    assert not any("Current buyer goals:" in item.value for item in app.markdown)
    assert not any("Required practice IDs to retrieve" in item.value for item in app.markdown)
    assert not app.exception


def test_assistant_failure_retains_question_and_conversation(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)

    def fail(*args, **kwargs):
        raise ValueError("Provider unavailable")

    monkeypatch.setattr(ai, "investigate", fail)
    app = start()
    workspace(app, "Acquisition assistant")
    element(app.text_area, "Ask SERA").set_value("Find California practices")
    click(app, "Send")
    assert element(app.text_area, "Ask SERA").value == "Find California practices"
    assert app.session_state["history"] == []
    assert app.session_state["chat"] == []
    assert any("could not finish" in error.value for error in app.error)
    assert not app.exception


def test_browse_details_save_then_reopen_membership(app_env):
    storage = ListStorage()
    list_id = storage.create("Demo shortlist")
    app = start()
    app.button(key="details_SERA-001").click().run()
    assert any("Seller legal disclosures" in item.value for item in app.markdown)
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Financials",
        "Property & lease",
        "Due diligence",
        "Area & patients",
        "Sources",
    ]
    # AppTest runs the whole script on interactions instead of dialog fragments.
    # Exercise the exact saving component in a normal rerun context; browser QA
    # covers the dialog interaction itself.
    app = AppTest.from_string("""
from app import save_controls
from sera.catalog import load_practices
from sera.storage import ListStorage
storage = ListStorage()
save_controls(load_practices()[0], storage, storage.load())
""").run()
    element(app.multiselect, "Save to lists").set_value([list_id])
    click(app, "Update saved lists")
    assert storage.load().lists[0].practice_ids == ["SERA-001"]
    assert app.session_state["list_notice"] == "Saved-list membership updated."
    assert element(app.multiselect, "Save to lists").value == [list_id]
    assert not app.exception


def test_newly_created_list_is_selected_and_names_fail_in_context(app_env):
    storage = ListStorage()
    storage.create("First")
    app = start()
    workspace(app, "Saved lists")
    element(app.text_input, "New list name").set_value("Second")
    click(app, "Create list")
    assert element(app.text_input, "List name").value == "Second"
    element(app.text_input, "List name").set_value("First")
    click(app, "Save name")
    assert any("could not be saved" in item.value for item in app.error)
    assert element(app.text_input, "List name").value == "First"
    assert [item.name for item in storage.load().lists] == ["First", "Second"]
    assert not app.exception


def test_facts_only_assessment_warning_is_visible_in_chat(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai,
        "investigate",
        lambda question, *args, **kwargs: dict(
            answer="Recorded fictional facts",
            calls=[],
            sources=[],
            history=[HumanMessage(content=question), AIMessage(content="Recorded fictional facts")],
            status="facts_only",
            warnings=["Generated advice failed evidence checks; recorded facts are shown."],
        ),
    )
    app = start()
    workspace(app, "Acquisition assistant")
    element(app.text_area, "Ask SERA").set_value("Investigate SERA-001")
    click(app, "Send")
    assert any("SERA could not support a complete assessment" in item.value for item in app.warning)
    assert not any("failed evidence checks" in item.value for item in app.warning)
    assert len(app.chat_message) == 2
    assert not app.exception


def test_ask_sera_shows_readable_sources_without_developer_panel(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai,
        "investigate",
        lambda question, *args, **kwargs: dict(
            answer="Recorded practice evidence",
            history=[
                HumanMessage(content=question),
                AIMessage(content="Recorded practice evidence"),
            ],
            calls=[{"tool": "get_practice_details", "arguments": {"practice_id": "SERA-001"}}],
            sources=[
                {
                    "id": "SERA-001-S1",
                    "label": "Seller listing",
                    "kind": "Seller disclosure",
                    "date": "2026-01-01",
                }
            ],
        ),
    )
    app = start()
    workspace(app, "Acquisition assistant")
    element(app.text_area, "Ask SERA").set_value("Investigate SERA-001")
    click(app, "Send")
    assert any("Source details" in item.label for item in app.expander)
    assert any("Seller listing" in item.value for item in app.markdown)
    assert any("Reference: SERA-001-S1" in item.value for item in app.caption)
    assert not app.json
    assert not any("How this answer was produced" in item.label for item in app.expander)
    assert not any("get_practice_details" in item.value for item in app.markdown)
    assert not app.exception


def test_first_practice_can_create_named_list_without_leaving_details(app_env):
    # Exercise the dialog's exact save component without AppTest fragment limits.
    app = AppTest.from_string("""
from app import save_controls
from sera.catalog import load_practices
from sera.storage import ListStorage
storage = ListStorage()
save_controls(load_practices()[0], storage, storage.load())
""").run()
    element(app.text_input, "New list name").set_value("My first shortlist")
    click(app, "Create list & save")
    stored = ListStorage().load().lists
    assert len(stored) == 1
    assert stored[0].name == "My first shortlist"
    assert stored[0].practice_ids == ["SERA-001"]
    assert app.session_state["list_notice"].startswith("List created and practice saved")
    assert element(app.multiselect, "Save to lists").value == [stored[0].id]
    assert not app.exception


def test_comparison_is_compact_and_full_evidence_has_readable_labels(app_env):
    storage = ListStorage()
    list_id = storage.create("Evidence comparison", practice_ids=["SERA-001", "SERA-002"])
    app = start()
    workspace(app, "Saved lists")
    select_comparison(app, ["SERA-001", "SERA-002"])
    table = comparison_markup(app)
    assert table.count('<th scope="row">') == 11
    assert "Practice overview" not in table
    assert "Seller legal disclosures" not in table
    assert "Reported annual revenue (not profit)" in table
    assert "Calendar year 2025" in table
    app.button(key="details_SERA-002").click().run()
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Financials",
        "Property & lease",
        "Due diligence",
        "Area & patients",
        "Sources",
    ]
    prose = "\n".join(item.value for item in app.markdown)
    assert "previously disclosed a lease-service-charge dispute" in prose
    assert "Reporting period:" in prose
    assert "• Asking price" in prose
    assert "• Patient household income" not in prose
    assert "Mean household income" in prose
    assert "reporting_period:" not in prose
    assert "asking_price" not in prose
    assert "patient_household_income" not in prose
    assert ListStorage().load().lists[0].id == list_id
    assert not app.exception


def test_empty_question_example_does_not_promise_saved_list_context(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    app = start()
    workspace(app, "Acquisition assistant")
    click(app, "Send")
    assert any("choose a starter prompt" in info.value for info in app.info)
    assert not any("my shortlist" in info.value for info in app.info)
    assert not app.exception


def test_currency_is_literal_and_private_correction_warnings_stay_hidden(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    answer = "Recorded asking price is $650,000 and reported revenue is $850,000 [SERA-001-S1]."
    result = dict(
        answer=answer,
        history=[HumanMessage(content="Review SERA-001"), AIMessage(content=answer)],
        calls=[],
        sources=[],
        status="facts_only",
        warnings=["Revenue is seller reported and unverified; remove claims of verified revenue"],
    )
    monkeypatch.setattr(ai, "investigate", lambda *args, **kwargs: result)
    storage = ListStorage()
    storage.create("Currency", practice_ids=["SERA-001", "SERA-002"])
    app = start()
    workspace(app, "Saved lists")
    select_comparison(app, ["SERA-001", "SERA-002"])
    click(app, "Generate AI comparison")
    expected = (
        r"Recorded asking price is \$650,000 and reported revenue is \$850,000 [SERA-001-S1]."
    )
    assert any(item.value == expected for item in app.markdown)
    assert result["answer"] == answer
    assert len(app.warning) == 1
    assert "could not support a complete assessment" in app.warning[0].value
    assert not any("remove claims" in item.value for item in app.warning)
    click(app, "Ask a follow-up about this assessment")
    workspace(
        app, "Acquisition assistant"
    )  # AppTest does not consume frontend navigation messages.
    assert any(item.value == expected for item in app.markdown)
    assert len(app.warning) == 1
    assert not any("remove claims" in item.value for item in app.warning)
    assert not app.exception


def test_existing_currency_escapes_are_not_duplicated():
    from app import buyer_answer_markdown

    text = r"Price \$650,000; revenue $850,000 [SERA-001-S1]."
    assert buyer_answer_markdown(text) == r"Price \$650,000; revenue \$850,000 [SERA-001-S1]."


def test_zero_price_cap_is_distinct_from_no_cap_and_reset(app_env):
    app = start()
    click(app, "Set filters manually")
    assert app.session_state["filters"].max_price is None
    assert not element(app.checkbox, "Use a maximum asking price").value
    assert element(app.number_input, "Maximum asking price ($)").disabled
    element(app.checkbox, "Use a maximum asking price").check().run()
    assert not element(app.number_input, "Maximum asking price ($)").disabled
    assert element(app.number_input, "Maximum asking price ($)").value == 0
    click(app, "Apply filters")
    assert app.session_state["filters"].max_price == 0
    assert any("No fictional records match" in info.value for info in app.info)
    click(app, "Edit filters")
    click(app, "Reset all filters")
    assert app.session_state["filters"].max_price is None
    assert not element(app.checkbox, "Use a maximum asking price").value
    assert element(app.number_input, "Maximum asking price ($)").disabled
    assert not app.exception


def test_suggested_zero_cap_remains_zero_when_applied(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai, "extract_filters", lambda _: SearchSuggestion(filters=Filters(max_price=0))
    )
    app = start()
    element(app.text_area, "Describe your ideal practice").set_value(
        "A practice with an asking price of zero"
    ).run()
    click(app, "Suggest editable filters")
    assert element(app.checkbox, "Use a maximum asking price").value
    assert element(app.number_input, "Maximum asking price ($)").value == 0
    click(app, "Apply filters")
    assert app.session_state["filters"].max_price == 0
    assert not app.exception


def test_catalog_paginates_distinct_practices_and_filter_change_resets_page(app_env):
    records = load_practices()
    eligible = search(records, Filters())
    app = start()
    first_page = visible_practice_ids(app)
    assert first_page == [practice.id for practice in eligible[:6]]
    assert len(first_page) == 6
    assert element(app.button, "Previous").disabled
    card_markup = "\n".join(
        item.value for item in app.markdown if 'class="sera-card"' in item.value
    )
    for practice in eligible[:6]:
        assert f"<h3>{escape(practice.name)}</h3>" in card_markup
        assert practice.id not in card_markup
    click(app, "Next")
    second_page = visible_practice_ids(app)
    assert second_page == [practice.id for practice in eligible[6:12]]
    assert not set(first_page).intersection(second_page)
    assert not element(app.button, "Previous").disabled
    click(app, "Previous")
    assert visible_practice_ids(app) == first_page
    click(app, "Next")
    click(app, "Set filters manually")
    assert not visible_practice_ids(app)
    element(app.multiselect, "States · all 50 available").set_value(["CA"]).run()
    click(app, "Apply filters")
    filtered = search(records, Filters(states=["CA"]))
    assert visible_practice_ids(app) == [practice.id for practice in filtered[:6]]
    assert app.session_state["result_page"] == 0
    assert not app.exception


def test_search_review_results_stages_hide_unrelated_controls_and_cards(app_env):
    app = start()
    assert len(visible_practice_ids(app)) == 6
    assert any(item.label == "Describe your ideal practice" for item in app.text_area)
    assert not app.multiselect
    click(app, "Set filters manually")
    assert element(app.multiselect, "States · all 50 available").value == []
    assert not visible_practice_ids(app)
    assert not any(item.label == "Describe your ideal practice" for item in app.text_area)
    element(app.multiselect, "States · all 50 available").set_value(["CA"]).run()
    click(app, "Apply filters")
    assert visible_practice_ids(app)
    assert not app.multiselect
    assert element(app.button, "Edit filters")
    click(app, "Edit filters")
    assert not visible_practice_ids(app)
    assert element(app.multiselect, "States · all 50 available").value == ["CA"]
    click(app, "Reset all filters")
    assert app.session_state["filters"] == Filters()
    assert element(app.multiselect, "States · all 50 available").value == []
    assert not visible_practice_ids(app)
    element(app.multiselect, "States · all 50 available").set_value(["AK"]).run()
    click(app, "Discard unapplied changes")
    assert app.session_state["filters"] == Filters()
    assert len(visible_practice_ids(app)) == 6
    assert not app.multiselect
    assert not app.exception


def test_answers_show_practice_names_but_keep_internal_history_and_source_ids(app_env, monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: True)
    practice = load_practices()[0]
    reference = practice.sources[0].id
    raw_answer = f"{practice.id} has recorded evidence [{reference}]."
    result = dict(
        answer=raw_answer,
        calls=[],
        sources=[practice.sources[0].model_dump()],
        history=[HumanMessage(content=f"Review {practice.id}"), AIMessage(content=raw_answer)],
        status="complete",
        warnings=[],
    )
    monkeypatch.setattr(ai, "investigate", lambda *args, **kwargs: result)
    app = start()
    workspace(app, "Acquisition assistant")
    element(app.text_area, "Ask SERA").set_value(f"Review {practice.id}")
    click(app, "Send")
    assert any(
        item.value == f"{practice.name} has recorded evidence [{reference}]."
        for item in app.markdown
    )
    assert any(item.value == f"Review {practice.name}" for item in app.markdown)
    assert any(f"Reference: {reference}" in item.value for item in app.caption)
    assert result["answer"] == raw_answer
    assert app.session_state["history"][-1].content == raw_answer
    assert app.session_state["history"][0].content == f"Review {practice.id}"
    assert app.session_state["last_trace"]["sources"][0]["id"] == reference
    assert not app.exception


def test_native_navigation_keeps_priorities_and_page_headings(app_env):
    app = start()
    element(app.text_area, "Acquisition priorities (optional)").set_value(
        "Seller transition support"
    ).run()
    original = app.session_state["filters"].model_copy(deep=True)
    workspace(app, "Saved lists")
    assert [item.value for item in app.title] == ["Your shortlists"]
    assert (
        element(app.text_area, "Acquisition priorities (optional)").value
        == "Seller transition support"
    )
    workspace(app, "Acquisition assistant")
    assert [item.value for item in app.title] == ["Ask SERA"]
    assert not any(item.label == "Start a new conversation" for item in app.button)
    assert app.session_state["filters"] == original
    workspace(app, "Explore practices")
    assert [item.value for item in app.title] == ["Find your next practice."]
    assert (
        element(app.text_area, "Acquisition priorities (optional)").value
        == "Seller transition support"
    )
    assert not app.exception


def test_card_and_dialog_save_controls_have_distinct_memberships_keys(app_env):
    storage = ListStorage()
    storage.create("Shared candidate", practice_ids=["SERA-001"])
    app = start()
    app.button(key="details_SERA-001").click().run()
    keys = [item.key for item in app.multiselect if item.label == "Save to lists"]
    assert any(key.startswith("explore_save_SERA-001_") for key in keys)
    assert any(key.startswith("dialog_save_SERA-001_") for key in keys)
    assert len(keys) == len(set(keys))
    assert not app.exception


def test_sorting_preserves_membership_and_resets_page(app_env):
    app = start()
    click(app, "Next")
    element(app.selectbox, "Sort practices").set_value("Price high–low").run()
    from sera.search_views import sorted_practices

    expected = sorted_practices(search(load_practices(), Filters()), "Price high–low")
    assert visible_practice_ids(app) == [item.id for item in expected[:6]]
    assert app.session_state["result_page"] == 0
    workspace(app, "Saved lists")
    workspace(app, "Explore practices")
    assert element(app.selectbox, "Sort practices").value == "Price high–low"
    assert visible_practice_ids(app) == [item.id for item in expected[:6]]
    assert not app.exception


def test_selected_shortlist_survives_native_navigation(app_env):
    storage = ListStorage()
    storage.create("First", practice_ids=["SERA-001"])
    second = storage.create("Second", practice_ids=["SERA-025"])
    app = start()
    workspace(app, "Saved lists")
    element(app.selectbox, "Choose list").set_value(second).run()
    workspace(app, "Acquisition assistant")
    workspace(app, "Saved lists")
    assert element(app.selectbox, "Choose list").value == second
    assert visible_practice_ids(app) == ["SERA-025"]
    assert not app.exception


def test_native_ma_scope_selection_drafts_then_one_explicit_request(app_env, monkeypatch):
    storage = ListStorage()
    lid = storage.create("M&A targets", practice_ids=["SERA-001", "SERA-025"])
    calls = []
    monkeypatch.setattr(ai, "configured", lambda: True)

    def investigate(question, context, history=None, required_ids=None):
        calls.append((question, required_ids))
        return dict(
            answer="Controlled diligence plan",
            history=[],
            calls=[],
            sources=[],
            status="complete",
            warnings=[],
        )

    monkeypatch.setattr(ai, "investigate", investigate)
    app = start()
    workspace(app, "Acquisition assistant")
    element(app.selectbox, "Choose from").set_value(lid).run()
    element(app.multiselect, "Practices").set_value(["SERA-001", "SERA-025"])
    click(app, "Use selected practices")
    assert app.session_state["chat_required_ids"] == ["SERA-001", "SERA-025"]
    click(app, "Assess a property")
    question = element(app.text_area, "Ask SERA").value
    assert "Riverbend Dermatology" in question and "Elmbrook Skin Center" in question
    assert calls == []
    workspace(app, "Explore practices")
    workspace(app, "Acquisition assistant")
    assert app.session_state["chat_required_ids"] == ["SERA-001", "SERA-025"]
    assert element(app.text_area, "Ask SERA").value == question
    click(app, "Send")
    assert element(app.text_area, "Ask SERA").value == ""
    assert calls == [(question, ["SERA-001", "SERA-025"])]
    assert any(item.key == "export_deal_notes" for item in app.get("download_button"))
    assert not app.exception
