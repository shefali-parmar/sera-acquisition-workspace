"""Search-state and ordering regressions using scripted extraction only."""

import pytest
from streamlit.testing.v1 import AppTest

from sera import ai
from sera.catalog import load_practices
from sera.models import Filters, SearchSuggestion
from sera.search_views import criteria_summary, sort_options, sorted_practices

HARNESS = """
import streamlit as st
from sera.models import Filters
from sera.search_views import browse_identity, search_controls
if "filters" not in st.session_state:
    st.session_state.filters = Filters()
if not search_controls():
    heading, scope = browse_identity()
    st.subheader(heading)
    st.caption(scope)
    st.caption("CATALOG SHOWN")
"""


def get(items, label):
    return next(item for item in items if item.label == label)


def click(app, label):
    return get(app.button, label).click().run()


def start(monkeypatch):
    monkeypatch.setattr(ai, "configured", lambda: False)
    app = AppTest.from_string(HARNESS, default_timeout=15).run()
    assert not app.exception
    return app


def test_sorts_preserve_catalog_order_handle_zero_unknowns_and_stable_ties():
    records = load_practices()[:5]
    names = ["Same", "same", "Alpha", "Zed", "Aardvark"]
    prices = [10, 10, 0, None, None]
    records = [
        record.model_copy(update={"name": name, "asking_price": price})
        for record, name, price in zip(records, names, prices)
    ]
    first, second, zero, unknown_z, unknown_a = records
    catalog = [second, first, unknown_z, zero, unknown_a]
    assert sort_options == ("Catalog order", "Price low–high", "Price high–low", "Name A–Z")
    assert sorted_practices(catalog) == catalog
    assert sorted_practices(catalog) is not catalog
    assert sorted_practices(catalog, "Price low–high") == [
        zero,
        first,
        second,
        unknown_z,
        unknown_a,
    ]
    assert sorted_practices(catalog, "Price high–low") == [
        first,
        second,
        zero,
        unknown_z,
        unknown_a,
    ]
    assert sorted_practices(catalog, "Name A–Z") == [unknown_a, zero, first, second, unknown_z]
    assert [record.asking_price for record in catalog] == [10, 10, None, 0, None]
    assert set(record.id for record in sorted_practices(catalog, "Name A–Z")) == set(
        record.id for record in catalog
    )
    assert sorted_practices([], "Price low–high") == []
    with pytest.raises(ValueError, match="supported sort"):
        sorted_practices(catalog, "Recommended")


def test_full_criteria_summary_includes_exact_boundaries_and_default_exclusions():
    summary = criteria_summary(Filters())
    assert "No price cap" in summary
    assert "Undisclosed prices excluded" in summary
    assert "Listed for sale" in summary and "Open to succession" in summary
    filters = Filters(
        states=["CA"],
        city="Sacramento",
        max_price=0,
        max_price_inclusive=False,
        min_patients=1000,
        min_years=5,
        min_sqft=1500,
        min_operatories=2,
        keyword="digital",
        include_undisclosed=True,
        statuses=[],
    )
    summary = criteria_summary(filters)
    for text in [
        "California",
        "Sacramento",
        "Under $0",
        "1,000+ patients",
        "5+ years operating",
        "1,500+ sq ft",
        "2+ operatories",
        "Keyword: digital",
        "Undisclosed prices included",
        "No availability selected",
    ]:
        assert text in summary
    assert "Up to $0" in criteria_summary(filters.model_copy(update={"max_price_inclusive": True}))


def test_initial_browse_identity_discloses_default_exclusions(monkeypatch):
    app = start(monkeypatch)
    assert any(item.value == "Browse available practices" for item in app.subheader)
    assert any(
        "unknown availability excluded" in item.value
        and "undisclosed prices excluded" in item.value
        for item in app.caption
    )
    assert "has_applied_search" not in app.session_state
    assert any(
        "Suggested criteria are unavailable" in item.value and "Set filters manually" in item.value
        for item in app.caption
    )
    assert get(app.button, "Suggest editable filters").disabled
    assert not get(app.button, "Set filters manually").disabled
    assert not app.multiselect
    assert not app.exception


def test_apply_chips_and_all_criteria_never_silently_change_filters_or_drafts(monkeypatch):
    app = start(monkeypatch)
    click(app, "Set filters manually")
    get(app.multiselect, "States · all 50 available").set_value(["CA"]).run()
    assert app.session_state["filters"].states == []
    assert not any(item.value == "CATALOG SHOWN" for item in app.caption)
    click(app, "Apply filters")
    assert app.session_state["has_applied_search"] is True
    assert app.session_state["filters"].states == ["CA"]
    assert not app.multiselect
    assert any(item.value == "Practices matching your criteria" for item in app.subheader)
    app.button(key="criteria_chip_location").click().run()
    assert get(app.multiselect, "States · all 50 available").value == ["CA"]
    get(app.multiselect, "States · all 50 available").set_value(["AK"]).run()
    assert app.session_state["filters"].states == ["CA"]
    click(app, "Revise request")
    assert any(item.value == "Current applied matches" for item in app.subheader)
    click(app, "All criteria")
    assert get(app.multiselect, "States · all 50 available").value == ["AK"]
    assert app.session_state["filters"].states == ["CA"]
    assert app.session_state["has_applied_search"] is True
    click(app, "Discard unapplied changes")
    assert app.session_state["filter_draft"].states == ["CA"]
    assert app.session_state["filters"].states == ["CA"]
    assert not app.multiselect
    assert not app.exception


def test_reset_explicitly_restores_default_scope_and_stays_in_review(monkeypatch):
    app = start(monkeypatch)
    click(app, "Set filters manually")
    get(app.multiselect, "States · all 50 available").set_value(["CA"]).run()
    click(app, "Apply filters")
    click(app, "Edit filters")
    click(app, "Reset all filters")
    assert app.session_state["filters"] == Filters()
    assert app.session_state["filter_draft"] == Filters()
    assert app.session_state["has_applied_search"] is False
    assert app.session_state["result_page"] == 0
    assert get(app.multiselect, "States · all 50 available").value == []
    assert not any(item.value == "CATALOG SHOWN" for item in app.caption)
    assert not app.exception


def test_suggestion_approval_and_revision_keep_applied_identity_until_apply(monkeypatch):
    app = start(monkeypatch)
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai,
        "extract_filters",
        lambda _: SearchSuggestion(
            filters=Filters(max_price=0, max_price_inclusive=False),
            preferences=["Owner transition support"],
            unverifiable=["Verified profit"],
        ),
    )
    get(app.text_area, "Describe your ideal practice").set_value("A zero-price opportunity").run()
    click(app, "Suggest editable filters")
    assert app.session_state["filters"].max_price is None
    assert app.session_state.get("has_applied_search", False) is False
    assert "search_preferences" not in app.session_state
    assert get(app.number_input, "Maximum asking price ($)").value == 0
    assert not get(app.checkbox, "Include practices exactly at the price cap").value
    assert not any(item.value == "CATALOG SHOWN" for item in app.caption)
    click(app, "Apply filters")
    assert app.session_state["has_applied_search"] is True
    assert app.session_state["filters"].max_price == 0
    assert app.session_state["search_preferences"] == ["Owner transition support"]
    assert app.session_state["search_unverifiable"] == ["Verified profit"]
    click(app, "Change search")
    get(app.text_area, "Describe your ideal practice").set_value("A new unapplied request").run()
    assert any(item.value == "Current applied matches" for item in app.subheader)
    assert app.session_state["filters"].max_price == 0
    assert app.session_state["has_applied_search"] is True
    assert not app.exception
