"""Factual presentation checks, independent of model, storage, and app routing."""

import html

from streamlit.testing.v1 import AppTest

from sera.catalog import fact_sheet, load_practices, money, operating_years, room_summary
from sera.models import Filters
from sera.practice_views import comparison_html, missing_information


def test_comparison_wraps_actual_names_and_retains_exact_budget_semantics():
    practice = load_practices()[0]
    at_price = Filters(max_price=practice.asking_price, max_price_inclusive=False)
    rendered = comparison_html([practice], at_price)
    assert f"<span>{html.escape(practice.name, quote=True)}</span>" in rendered
    assert "Above asking-price budget" in rendered
    assert "white-space:normal" in rendered
    assert "overflow-wrap:anywhere" in rendered
    assert "overflow-x:auto" in rendered
    assert '<th scope="col">' in rendered
    assert '<th scope="row">' in rendered
    assert practice.id not in rendered
    assert html.escape(practice.revenue_period, quote=True) in rendered
    assert html.escape(practice.patient_period, quote=True) in rendered
    assert "Reported annual revenue (not profit)" in rendered
    inclusive = comparison_html([practice], Filters(max_price=practice.asking_price))
    assert "Within asking-price budget" in inclusive


def test_comparison_escapes_every_dynamic_field_including_names_and_periods():
    practice = load_practices()[0].model_copy(
        update={
            "name": '<script>alert("name")</script>',
            "city": "<b>City & district</b>",
            "specialty": '<img src=x onerror="alert(1)">',
            "revenue_period": '<script>alert("period")</script>',
            "patient_period": "2025 & <patient period>",
        }
    )
    rendered = comparison_html([practice], Filters())
    for value in [
        practice.name,
        practice.city,
        practice.specialty,
        practice.revenue_period,
        practice.patient_period,
    ]:
        assert value not in rendered
        assert html.escape(value, quote=True) in rendered
    assert "<script>" not in rendered
    assert "<img " not in rendered


def test_comparison_preserves_unknowns_and_missing_periods():
    practice = load_practices()[0].model_copy(
        update={
            "specialty": "General dentistry",
            "asking_price": None,
            "annual_revenue": None,
            "active_patients": None,
            "founding_year": None,
            "sqft": None,
            "operatories": None,
            "revenue_period": None,
            "patient_period": None,
        }
    )
    rendered = comparison_html([practice], Filters(max_price=0))
    assert "Price undisclosed" in rendered
    assert "Budget unverified" in rendered
    assert rendered.count("Reporting period unknown") == 2
    assert "Unknown size" in rendered
    assert "Unknown operatories" in rendered
    assert "Revenue reporting period" in missing_information(practice)
    assert "Patient reporting period" in missing_information(practice)
    assert comparison_html([], Filters()) == ""


def test_detail_tabs_preserve_full_evidence_and_invoke_injected_controls():
    practice = load_practices()[0]
    app = AppTest.from_string("""
import streamlit as st
from sera.catalog import load_practices
from sera.practice_views import render_practice_details
st.session_state.calls = []
def save():
    st.session_state.calls.append("save")
    st.caption("Save action marker")
def analyze():
    st.session_state.calls.append("analysis")
    st.caption("Analysis action marker")
render_practice_details(load_practices()[0], save, analyze)
""").run()
    assert not app.exception
    assert app.session_state["calls"] == ["save", "analysis"]
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Financials",
        "Property & lease",
        "Due diligence",
        "Area & patients",
        "Sources",
    ]
    assert app.subheader[0].value == practice.name
    assert app.metric[0].value == money(practice.asking_price)
    assert app.metric[1].value == f"{practice.active_patients:,}"
    assert app.metric[2].value == str(operating_years(practice))
    prose = "\n".join(item.value for item in app.markdown)
    captions = "\n".join(item.value for item in app.caption)
    assert practice.description in prose
    for event in practice.history:
        assert event in prose
    assert practice.availability_evidence in prose
    assert practice.availability_date in captions
    assert practice.revenue_period in prose
    assert practice.patient_period in prose
    assert practice.legal_disclosures in prose
    assert practice.legal_research_status in prose
    for evidence in [
        practice.crime,
        practice.patient_household_income,
        practice.area_household_income,
    ]:
        if evidence:
            for value in evidence.values():
                assert str(value) in prose
    for source in practice.sources:
        assert source.label in prose
        assert source.kind in captions
        assert source.date in captions
        assert source.id in captions
    assert "Asking price is not total acquisition cost" in captions
    assert "Revenue is not profit" in captions
    assert "fictional" in captions.lower()
    assert "reporting_period:" not in prose
    assert not app.json
    assert not any("SERA-" in item.value for item in app.subheader)
    save_index = next(i for i, item in enumerate(app.caption) if item.value == "Save action marker")
    availability_index = next(
        i for i, item in enumerate(app.caption) if item.value.startswith("Availability recorded:")
    )
    assert save_index < availability_index


def test_detail_missing_evidence_is_readable_and_explicit():
    app = AppTest.from_string("""
from sera.catalog import load_practices
from sera.practice_views import render_practice_details
practice = load_practices()[0].model_copy(update={
    "asking_price":None, "revenue_period":None, "patient_period":None,
    "patient_household_income":None, "history":[],
})
render_practice_details(practice, lambda:None, lambda:None)
""").run()
    assert not app.exception
    assert app.metric[0].value == "Undisclosed"
    prose = "\n".join(item.value for item in app.markdown)
    captions = "\n".join(item.value for item in app.caption)
    assert "Revenue reporting period: Unknown" in prose
    assert "Patient reporting period: Unknown" in prose
    assert "• Asking price" in prose
    assert "• Patient household income" in prose
    assert "Unknown — no supplied evidence" in captions
    assert "No ownership or transition history supplied" in captions
    assert "patient_household_income" not in prose


def test_unknown_legal_statuses_are_gaps_without_inferred_legal_conclusions():
    practice = load_practices()[0].model_copy(
        update={
            "legal_disclosures": "Unknown — no seller legal disclosure supplied.",
            "legal_research_status": "Unknown — independent records have not been researched.",
        }
    )
    missing = missing_information(practice)
    assert "Seller legal disclosures (unknown)" in missing
    assert "Independent legal research (unknown)" in missing
    disclosed = practice.model_copy(
        update={
            "legal_disclosures": "Seller disclosed an unresolved lease dispute.",
            "legal_research_status": "Independent review pending; outcome unknown.",
        }
    )
    # A disclosed concern or a pending review is not silently classified as missing or clean.
    assert "Seller legal disclosures (unknown)" not in missing_information(disclosed)
    assert "Independent legal research (unknown)" not in missing_information(disclosed)


def test_gap_summary_is_visible_before_overview_and_preserves_full_gap_list():
    app = AppTest.from_string("""
from sera.catalog import load_practices
from sera.practice_views import render_practice_details
practice = load_practices()[0].model_copy(update={
    "asking_price": None, "annual_revenue": None, "sqft": None,
    "patient_household_income": None,
    "legal_disclosures": "Unknown — seller legal disclosures not supplied.",
    "legal_research_status": "Unknown — independent review not supplied.",
})
render_practice_details(practice, lambda:None, lambda:None)
""").run()
    assert not app.exception
    prose = [item.value for item in app.markdown]
    gap_index = next(
        index for index, value in enumerate(prose) if 'class="sera-evidence-gaps"' in value
    )
    summary = prose[gap_index]
    assert "Asking price" in summary
    assert "Reported annual revenue" in summary
    assert "Seller legal disclosures (unknown)" in summary
    assert "Independent legal research (unknown)" in summary
    assert gap_index < next(
        index for index, value in enumerate(prose) if "Practice history" in value
    )
    assert any("• Practice size" in value for value in prose)
    assert any("• Patient household income" in value for value in prose)


def test_comparison_keeps_exact_periods_beneath_values_and_is_keyboard_scrollable():
    practice = load_practices()[0]
    rendered = comparison_html([practice], Filters())
    assert (
        '<span class="sera-comparison-value">'
        + money(practice.annual_revenue)
        + "</span><small>"
        + html.escape(practice.revenue_period, quote=True)
        + "</small>"
    ) in rendered
    assert (
        '<span class="sera-comparison-value">'
        + f"{practice.active_patients:,}"
        + "</span><small>"
        + html.escape(practice.patient_period, quote=True)
        + "</small>"
    ) in rendered
    assert 'tabindex="0" role="region"' in rendered
    assert "Scroll sideways to compare practices" in rendered


def test_complete_profiles_render_financials_and_applicable_property_costs():
    records = load_practices()
    for occupancy in ("Leased", "Owned"):
        practice = next(p for p in records if p.premises and p.premises.occupancy == occupancy)
        app = AppTest.from_string(f"""
from sera.catalog import load_practices
from sera.practice_views import render_practice_details
practice = next(p for p in load_practices() if p.id == {practice.id!r})
render_practice_details(practice, lambda:None, lambda:None)
""").run()
        assert not app.exception
        prose = "\n".join(item.value for item in app.markdown)
        captions = "\n".join(item.value for item in app.caption)
        assert practice.premises.address in prose
        assert practice.operations.transition_support in prose
        assert practice.financials.normalization_notes in prose
        assert room_summary(practice) in captions
        assert practice.premises.source in captions
        assert practice.financials.source in captions
        assert not missing_information(practice)
        assert not any('class="sera-evidence-gaps"' in item.value for item in app.markdown)
        assert "Modeled normalized EBITDA" in [m.label for m in app.metric]
        if occupancy == "Leased":
            assert "Annual base rent" in [m.label for m in app.metric]
            assert "Separate property asking price" not in [m.label for m in app.metric]
            assert practice.premises.lease_expires in prose
        else:
            assert "Separate property asking price" in [m.label for m in app.metric]
            assert "Annual base rent" not in [m.label for m in app.metric]
            assert "excluded from the practice asking price" in captions
        assert "fictional and unaudited" in captions


def test_fact_sheets_preserve_complete_profiles_and_conditional_room_types():
    for practice in load_practices():
        sheet = fact_sheet(practice)
        assert (
            practice.financials.source
            in sheet["Financial profile (fictional seller model, not audited)"]
        )
        assert (
            str(practice.financials.normalized_ebitda)
            in sheet["Financial profile (fictional seller model, not audited)"]
        )
        assert practice.premises.source in sheet["Premises / property profile (fictional)"]
        assert practice.operations.source in sheet["Operations profile (fictional)"]
        assert room_summary(practice) in sheet["Size"]
        assert (
            sheet["Missing evidence"] == "asking_price"
            if practice.asking_price is None
            else "No missing fields" in sheet["Missing evidence"]
        )
        if practice.premises.occupancy == "Owned":
            assert "annual base rent" not in sheet["Premises / property profile (fictional)"]
        else:
            assert "property asking price" not in sheet["Premises / property profile (fictional)"]
