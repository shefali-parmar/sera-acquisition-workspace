import json

import pytest
from pydantic import ValidationError

from sera.ai import get_practice_details, search_practices
from sera.catalog import budget_fit, fact_sheet, load_practices, operating_years, search
from sera.models import STATES, Filters, SearchSuggestion
from sera.storage import ListStorage


def test_combined_filters():
    found = search(
        load_practices(),
        Filters(
            specialties=["Dermatology"],
            states=["CA"],
            max_price=1500000,
            min_patients=1000,
            min_years=10,
        ),
    )
    assert found
    assert all(
        p.specialty == "Dermatology"
        and p.state == "CA"
        and p.asking_price <= 1500000
        and p.active_patients >= 1000
        and operating_years(p) >= 10
        for p in found
    )


def test_missing_and_budget():
    records = load_practices()
    unknown = next(
        p for p in records if p.asking_price is None and p.status != "Availability unknown"
    )
    assert "Budget unverified" in budget_fit(unknown, 99999999)
    assert unknown not in search(records, Filters(include_undisclosed=False))
    assert unknown in search(records, Filters(include_undisclosed=True))
    assert all(
        p.active_patients is not None
        for p in search(records, Filters(min_patients=1, include_undisclosed=True))
    )
    assert all(
        p.founding_year is not None
        for p in search(records, Filters(min_years=1, include_undisclosed=True))
    )
    assert (
        "Unknown"
        in fact_sheet(records[0].model_copy(update={"founding_year": None}))[
            "Founded / approximate years"
        ]
    )


def test_locations_status():
    assert len(STATES) == 50
    assert search(load_practices(), Filters(states=["AK"], include_undisclosed=True)) == []
    assert search(load_practices(), Filters(city="Atlantis", include_undisclosed=True)) == []
    assert all(
        p.status != "Availability unknown"
        for p in search(load_practices(), Filters(include_undisclosed=True))
    )
    assert all(
        p.city == "Sacramento"
        for p in search(load_practices(), Filters(city=" sacramento ", include_undisclosed=True))
    )


def test_storage(tmp_path):
    path = tmp_path / "saved.json"
    storage = ListStorage(path)
    a = storage.create("First")
    b = storage.create("Second")
    storage.update(a, practice_ids=["SERA-001", "SERA-001"])
    storage.update(b, practice_ids=["SERA-001"])
    assert ListStorage(path).load().lists[0].practice_ids == ["SERA-001"]
    storage.update(a, name="Renamed", practice_ids=[])
    assert storage.load().lists[0].name == "Renamed"
    storage.update(a, delete=True)
    assert len(storage.load().lists) == 1
    path.write_text("broken")
    with pytest.raises(ValidationError):
        storage.load()
    assert path.read_text() == "broken"


def test_validation_and_tools():
    for invalid in [
        {"states": ["XX"]},
        {"max_price": -1},
        {"specialties": ["Magic"]},
        {"radius": 20},
        {"statuses": ["Retiring inferred"]},
    ]:
        with pytest.raises(ValidationError):
            Filters.model_validate(invalid)
    suggestion = SearchSuggestion.model_validate(
        {
            "filters": {"states": ["CA"]},
            "unverifiable": ["ROI"],
            "clarification": "What numeric operating-year minimum?",
        }
    )
    assert suggestion.unverifiable == ["ROI"]
    output = json.loads(search_practices.invoke({"filters": {"states": ["CA"]}}))
    assert output["total"] > 0
    assert json.loads(get_practice_details.invoke({"practice_id": "SERA-001"}))["fictional"]
    assert "error" in json.loads(get_practice_details.invoke({"practice_id": "missing"}))


def test_missing_key(monkeypatch):
    from sera import ai

    monkeypatch.setenv("SERA_AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not ai.configured()
    with pytest.raises(ValueError):
        ai.model()


def test_ui_offline(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("SERA_AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from sera.catalog import ROOT

    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert any("AI assessments unavailable" in item.value for item in app.caption)
    app.switch_page("screens/shortlists.py").run()
    assert not app.exception
    app.switch_page("screens/ask_sera.py").run()
    assert not app.exception


def test_real_agent_graph_with_scripted_model(monkeypatch):
    """Offline protocol check, not an OpenAI response or quality evaluation."""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from sera import ai

    class ScriptedModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "offline-test"

        def bind_tools(self, tools, **kwargs):
            assert {t.name for t in tools} == {
                "search_practices",
                "get_practice_details",
            }
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            tools = [m for m in messages if isinstance(m, ToolMessage)]
            if not tools:
                answer = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_practices",
                            "args": {"filters": {"states": ["CA"]}},
                            "id": "s",
                        }
                    ],
                )
            elif len(tools) == 1:
                answer = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_practice_details",
                            "args": {"practice_id": "SERA-001"},
                            "id": "d",
                        }
                    ],
                )
            else:
                answer = AIMessage(
                    content="Recorded fictional facts: SERA-001-S1. AI interpretation: verify evidence."
                )
            return ChatResult(generations=[ChatGeneration(message=answer)])

    monkeypatch.setattr(ai, "model", lambda: ScriptedModel())
    result = ai.investigate("Find dermatology practices in California", "California")
    assert [c["tool"] for c in result["calls"]] == [
        "search_practices",
        "get_practice_details",
    ]
    assert len(result["history"]) == 2
    assert result["status"] == "complete"


def test_ui_filters_details_and_list_editing(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    import sera.storage as module
    from sera.catalog import ROOT

    original = module.ListStorage
    monkeypatch.setattr(module, "ListStorage", lambda: original(tmp_path / "lists.json"))
    monkeypatch.setenv("SERA_AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    next(b for b in app.button if b.label == "Set filters manually").click().run()
    app.multiselect(key="states0").set_value(["AK"])
    next(b for b in app.button if b.label == "Apply filters").click().run()
    assert not app.exception
    assert any("No fictional records match" in x.value for x in app.info)
    assert not app.multiselect
    next(b for b in app.button if b.label == "Edit filters").click().run()
    assert app.multiselect(key="states0").value == ["AK"]
    app.multiselect(key="states0").set_value([])
    next(b for b in app.button if b.label == "Apply filters").click().run()
    next(b for b in app.button if b.label == "View practice").click().run()
    assert not app.exception
    assert any("Seller legal disclosures" in x.value for x in app.markdown)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.switch_page("screens/shortlists.py").run()
    next(t for t in app.text_input if t.label == "New list name").set_value("Demo")
    next(b for b in app.button if b.label == "Create list").click().run()
    assert not app.exception
    next(m for m in app.multiselect if m.label.startswith("Practices in this list")).set_value(
        ["SERA-001", "SERA-025"]
    )
    next(b for b in app.button if b.label == "Save list changes").click().run()
    assert not app.exception
    assert len(original(tmp_path / "lists.json").load().lists[0].practice_ids) == 2
    for pid in ["SERA-001", "SERA-025"]:
        next(
            w for w in app.checkbox if w.label == "Select for comparison" and w.key.endswith(pid)
        ).check().run()
    next(b for b in app.button if b.label == "Compare selected").click().run()
    table = next(
        item.value for item in app.markdown if '<table class="sera-comparison"' in item.value
    )
    assert table.count('<th scope="col">') == 3
    records = {practice.id: practice for practice in load_practices()}
    assert records["SERA-001"].name in table
    assert records["SERA-025"].name in table
    assert "SERA-001" not in table
    assert not next(b for b in app.button if b.label == "Delete list").value


def test_catalog_cache_refresh_and_isolation(tmp_path):
    """Caching must not hide edited source data or leak a caller's mutations."""
    path = tmp_path / "practices.json"
    record = load_practices()[0].model_dump()
    path.write_text(json.dumps([record]))
    loaded = load_practices(path)
    loaded[0].history.append("Caller-only change")
    assert "Caller-only change" not in load_practices(path)[0].history
    record["name"] = "Updated fictional practice"
    path.write_text(json.dumps([record]))
    assert load_practices(path)[0].name == record["name"]


def test_memberships_are_one_validated_write(tmp_path, monkeypatch):
    storage = ListStorage(tmp_path / "lists.json")
    first, second = storage.create("First"), storage.create("Second")
    writes = []
    original = storage.write

    def record_write(store):
        writes.append(store)
        original(store)

    monkeypatch.setattr(storage, "write", record_write)
    storage.set_memberships("SERA-001", [first, second])
    assert len(writes) == 1
    assert all(item.practice_ids == ["SERA-001"] for item in storage.load().lists)
    storage.set_memberships("SERA-001", [second])
    assert storage.load().lists[0].practice_ids == []
    before = storage.path.read_bytes()
    with pytest.raises(ValueError):
        storage.set_memberships("SERA-001", ["missing"])
    assert storage.path.read_bytes() == before
    with pytest.raises(ValidationError):
        storage.update(first, name=" ")
    assert storage.path.read_bytes() == before


def test_list_switching_keeps_edits_isolated(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    import sera.storage as module
    from sera.catalog import ROOT

    storage = ListStorage(tmp_path / "lists.json")
    first, second = storage.create("First"), storage.create("Second")
    storage.update(first, practice_ids=["SERA-001"])
    storage.update(second, practice_ids=["SERA-025"])
    monkeypatch.setattr(module, "ListStorage", lambda: storage)
    monkeypatch.setenv("SERA_AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.switch_page("screens/shortlists.py").run()
    next(widget for widget in app.text_input if widget.label == "List name").set_value(
        "Unsaved first draft"
    ).run()
    app.selectbox[0].set_value(second).run()
    assert (
        next(widget for widget in app.text_input if widget.label == "List name").value == "Second"
    )
    assert next(
        widget for widget in app.multiselect if widget.label.startswith("Practices in this list")
    ).value == ["SERA-025"]
    next(button for button in app.button if button.label == "Save list changes").click().run()
    assert storage.load().lists[0].name == "First"
    assert storage.load().lists[1].practice_ids == ["SERA-025"]


def test_assistant_submits_first_question_and_preserves_failed_turn(monkeypatch):
    """Exercise the form without an API call; failed requests must retain prior context."""
    from streamlit.testing.v1 import AppTest

    from sera import ai
    from sera.catalog import ROOT

    monkeypatch.setattr(ai, "configured", lambda: True)
    requests = []

    def investigate(question, goals, history=None, required_ids=None):
        requests.append(question)
        if len(requests) > 1:
            raise ValueError("Simulated failure")
        return {"answer": "Fictional assessment", "calls": [], "sources": [], "history": []}

    monkeypatch.setattr(ai, "investigate", investigate)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.switch_page("screens/ask_sera.py").run()
    submit = next(button for button in app.button if button.label == "Send")
    assert not submit.disabled
    app.text_area(key="assistant_question").set_value("Find practices")
    submit.click().run()
    assert requests == ["Find practices"]
    app.text_area(key="assistant_question").set_value("Follow up")
    next(button for button in app.button if button.label == "Send").click().run()
    assert app.text_area(key="assistant_question").value == "Follow up"
    assert len(app.session_state["chat"]) == 2
    assert app.error
    next(
        button for button in app.button if button.label == "Start a new conversation"
    ).click().run()
    assert app.session_state["chat"] == []
    assert "last_trace" not in app.session_state


def test_ollama_client_is_local_and_has_no_paid_fallback(monkeypatch):
    from sera import ai

    monkeypatch.setenv("SERA_AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert ai.configured()
    assert ai.model().model == "qwen3:8b"
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:cloud")
    with pytest.raises(ValueError, match="local"):
        ai.model()
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://example.com")
    with pytest.raises(ValueError, match="local"):
        ai.model()


def test_follow_up_candidates_are_retained_but_new_search_is_independent():
    from langchain_core.messages import AIMessage

    from sera.ai import investigation_ids

    history = [AIMessage(content="Compared SERA-001 [SERA-001-S1] and SERA-025.")]
    assert investigation_ids("What changes if my budget drops?", history, None) == [
        "SERA-001",
        "SERA-025",
    ]
    assert investigation_ids("Find dentists in Texas", history, None) == []
    assert investigation_ids("Investigate SERA-007", history, None) == ["SERA-007"]


def test_agent_rejects_fabricated_sources_and_omitted_candidates(monkeypatch):
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, ToolMessage

    from sera import ai

    monkeypatch.setattr(ai, "model", lambda: None)
    answer = "SERA-001: recorded facts [SERA-001-S99]."

    def invoke(request, config):
        return {
            "messages": request["messages"]
            + [
                ToolMessage(
                    content=ai.get_practice_details.invoke({"practice_id": "SERA-001"}),
                    name="get_practice_details",
                    tool_call_id="one",
                ),
                ToolMessage(
                    content=ai.get_practice_details.invoke({"practice_id": "SERA-025"}),
                    name="get_practice_details",
                    tool_call_id="two",
                ),
                AIMessage(content=answer),
            ]
        }

    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(invoke=invoke))
    fallback = ai.investigate("Compare", "", required_ids=["SERA-001", "SERA-025"])
    assert fallback["status"] == "facts_only"
    assert "SERA-001-S99" not in fallback["answer"]
    assert any("unknown evidence source" in issue for issue in fallback["warnings"])
    answer = "SERA-001: recorded facts [SERA-001-S1]."
    fallback = ai.investigate("Compare", "", required_ids=["SERA-001", "SERA-025"])
    assert fallback["status"] == "facts_only"
    assert "SERA-001" in fallback["answer"] and "SERA-025" in fallback["answer"]
    assert any("Discuss every" in issue for issue in fallback["warnings"])


def test_assessment_can_continue_in_chat_without_losing_context(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage

    import app

    class Session(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    state = Session()
    monkeypatch.setattr(app.st, "session_state", state)
    result = {
        "history": [
            HumanMessage(content="Compare SERA-001 and SERA-025"),
            AIMessage(content="Recorded fictional assessment"),
        ],
        "answer": "Recorded fictional assessment",
    }
    app.continue_assessment(result, "snapshot goals", ["SERA-001", "SERA-025"])
    assert state.chat_context == "snapshot goals"
    assert state.chat_required_ids == ["SERA-001", "SERA-025"]
    assert state.workspace == "Acquisition assistant"
    assert state.history is result["history"]
    assert [turn["role"] for turn in state.chat] == ["assistant"]
    assert state.last_trace is result


def test_grounding_checks_distinguish_unverified_revenue():
    from sera.ai import answer_issues

    sources = [{"id": "SERA-001-S1"}]
    assert (
        answer_issues(
            "SERA-001 has not audited revenue [SERA-001-S1].", ["SERA-001"], {"SERA-001"}, sources
        )
        == []
    )
    assert answer_issues(
        "SERA-001 has audited revenue [SERA-001-S1].", ["SERA-001"], {"SERA-001"}, sources
    )
    assert answer_issues(
        "SERA-001 has a moderate-income patient base [SERA-001-S1].",
        ["SERA-001"],
        {"SERA-001"},
        sources,
    )


def test_one_corrective_revision_can_repair_missing_citations(monkeypatch):
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, ToolMessage

    from sera import ai

    invocations = []
    monkeypatch.setattr(ai, "model", lambda: None)

    def invoke(request, config):
        invocations.append(request)
        if len(invocations) == 1:
            messages = [
                ToolMessage(
                    content=ai.get_practice_details.invoke({"practice_id": "SERA-001"}),
                    name="get_practice_details",
                    tool_call_id="one",
                ),
                AIMessage(content="SERA-001 is a fictional practice."),
            ]
        else:
            assert "Required corrections" in request["messages"][-1].content
            messages = [
                AIMessage(
                    content="Recorded facts: SERA-001 [SERA-001-S1]. AI interpretation: investigate missing evidence."
                )
            ]
        return {"messages": request["messages"] + messages}

    monkeypatch.setattr(ai, "create_agent", lambda **kwargs: SimpleNamespace(invoke=invoke))
    result = ai.investigate("Investigate SERA-001", "")
    assert len(invocations) == 2
    assert "SERA-001-S1" in result["answer"]
    assert (
        len(result["history"]) == 2
    )  # The rejected draft is not retained as conversation context.
