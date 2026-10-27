"""Buyer-facing practice evidence and comparisons, without model or storage calls."""

import html
import re
from collections.abc import Callable

import streamlit as st

from sera.catalog import DENTAL_SPECIALTIES, budget_fit, money, operating_years, room_summary
from sera.design import COMPARISON_CSS
from sera.models import Filters, Practice

_MISSING_FIELDS = {
    "founding_year": "Founding year",
    "asking_price": "Asking price",
    "annual_revenue": "Reported annual revenue",
    "active_patients": "Active patient count",
    "sqft": "Practice size",
    "operatories": "Number of operatories",
    "revenue_period": "Revenue reporting period",
    "patient_period": "Patient reporting period",
    "crime": "Local crime statistics",
    "patient_household_income": "Patient household income",
    "area_household_income": "Area household income",
}


def missing_information(practice: Practice) -> list[str]:
    """Use buyer-readable labels without concealing missing periods or statistics."""
    missing = [
        label
        for field, label in _MISSING_FIELDS.items()
        if getattr(practice, field) is None
        and (field != "operatories" or practice.specialty in DENTAL_SPECIALTIES)
    ]
    for field, label in (
        ("legal_disclosures", "Seller legal disclosures (unknown)"),
        ("legal_research_status", "Independent legal research (unknown)"),
    ):
        if re.match(r"\s*unknown\b", getattr(practice, field), re.I):
            missing.append(label)
    return missing


def _gap_summary(practice: Practice) -> None:
    missing = missing_information(practice)
    if not missing:
        st.caption(
            "Demo profile complete. All evidence is simulated; real transactions require independent verification."
        )
        return
    priority = [
        label
        for label in (
            "Asking price",
            "Reported annual revenue",
            "Seller legal disclosures (unknown)",
            "Independent legal research (unknown)",
        )
        if label in missing
    ]
    remaining = [label for label in missing if label not in priority]
    visible = (priority + remaining)[:4]
    text = "; ".join(visible)
    if len(missing) > len(visible):
        text += ". More missing information in Due diligence."
    st.markdown(
        '<div class="sera-evidence-gaps"><strong>Evidence gaps:</strong> '
        + html.escape(text, quote=True)
        + "</div>",
        unsafe_allow_html=True,
    )


def _prose(value: object) -> str:
    # Currency must remain literal when a paragraph contains several dollar amounts.
    return re.sub(r"(?<!\\)\$(?=\d)", r"\\$", str(value))


def _write(value: object) -> None:
    st.write(_prose(value))


def _source_reference(practice: Practice, reference: str) -> str:
    source = next((source for source in practice.sources if source.id == reference), None)
    return (
        f"{source.label} · {source.date} · Reference: {source.id}"
        if source
        else f"Source reference: {reference}"
    )


def _evidence(practice: Practice, evidence: dict | None) -> None:
    if evidence is None:
        st.caption("Unknown — no supplied evidence.")
        return
    labels = {"source": "Source", "limitation": "Evidence limitation"}
    for field, value in evidence.items():
        label = labels.get(field, field.replace("_", " ").capitalize())
        rendered = _source_reference(practice, str(value)) if field == "source" else value
        _write(f"**{label}:** {rendered}")


def _operations(practice: Practice) -> None:
    operations = practice.operations
    if operations is None:
        return
    st.markdown("**Team & capacity**")
    _write(
        f"{operations.providers} providers · {operations.staff_fte:g} staff FTE · "
        f"{operations.weekly_open_hours:g} hours per week · {room_summary(practice)}"
    )
    _write(f"Annual visits: {operations.annual_visits:,}")
    _write("Patient reporting period: " + (practice.patient_period or "Unknown"))
    _write(
        "Payer mix: "
        + " · ".join(
            f"{name.replace('_', ' ').title()} {share:g}%"
            for name, share in operations.payer_mix.model_dump().items()
        )
    )
    st.markdown("**Equipment & transition**")
    for equipment in operations.equipment:
        _write("• " + equipment)
    _write(operations.transition_support)
    st.caption(_source_reference(practice, operations.source))


def _financials(practice: Practice) -> None:
    profile = practice.financials
    revenue, earnings = st.columns(2)
    revenue.metric("Reported annual revenue", money(practice.annual_revenue, missing="Unknown"))
    if profile:
        earnings.metric("Modeled normalized EBITDA", money(profile.normalized_ebitda))
        st.caption("EBITDA is earnings before interest, taxes, depreciation and amortization.")
    _write("Revenue reporting period: " + (practice.revenue_period or "Unknown"))
    if profile:
        st.caption(f"{profile.reporting_period} · {profile.accounting_basis}")
        st.markdown("**Operating expense model**")
        for label, value in (
            ("Payroll", profile.payroll_expense),
            ("Clinical supplies", profile.supplies_expense),
            ("Occupancy", profile.occupancy_expense),
            ("Other operating expenses", profile.other_operating_expense),
        ):
            _write(f"{label}: {money(value)}")
        _write(
            "Payroll includes replacement clinical compensation for the working owner."
            if profile.owner_compensation_included
            else "Owner compensation treatment is not supplied."
        )
        _write(profile.normalization_notes)
        st.caption(_source_reference(practice, profile.source))
    st.caption(
        "Revenue is not profit. Asking price is not total acquisition cost. "
        "The financial model is fictional and unaudited; normalized EBITDA is not net income, "
        "owner take-home pay, a valuation or a projected return."
    )


def _premises(practice: Practice) -> None:
    profile = practice.premises
    if profile is None:
        st.caption("Premises profile not supplied.")
        return
    st.markdown(f"**{profile.occupancy} · {profile.property_type}**")
    _write(profile.address)
    st.caption("Fictional address and property terms; no real property is offered for sale.")
    if profile.occupancy == "Leased":
        annual, cam = st.columns(2)
        annual.metric("Annual base rent", money(profile.annual_base_rent))
        cam.metric("Annual CAM", money(profile.annual_cam))
        st.caption(
            "CAM means common area maintenance charges. Base rent and CAM are separate costs."
        )
        _write(
            f"Total annual base rent + CAM: {money(profile.annual_base_rent + profile.annual_cam)}"
        )
        _write(f"Lease expires: {profile.lease_expires}")
        _write(f"Renewal options: {profile.renewal_options}")
        _write(f"Annual rent escalation: {profile.annual_escalation_percent:g}%")
        _write(
            "Landlord consent required: " + ("Yes" if profile.landlord_consent_required else "No")
        )
        _write("Assignment terms: " + profile.assignment_terms)
        st.caption("No property purchase is included in this leased-premises scenario.")
    else:
        st.metric("Separate property asking price", money(profile.property_asking_price))
        st.caption(
            "Real estate is offered separately. It is excluded from the practice asking price."
        )
        _write("Property transfer terms: " + profile.assignment_terms)
    st.markdown("**Suitability & access**")
    _write(f"Parking: {profile.parking_spaces} spaces")
    _write("Accessibility: " + profile.accessibility)
    _write("Permitted use: " + profile.permitted_use)
    _write("Property review: " + profile.review_status)
    st.caption(f"Scenario review date: {profile.review_date}")
    st.caption(_source_reference(practice, profile.source))


def render_practice_details(
    practice: Practice,
    save_controls_callback: Callable[[], None],
    analysis_controls_callback: Callable[[], None],
) -> None:
    """Render one factual record; injected callbacks supply saving and optional AI."""
    st.subheader(practice.name)
    st.caption(f"{practice.specialty} · {practice.city}, {practice.state} · {practice.status}")
    st.caption("Fictional practice and evidence. Confirm all information through due diligence.")
    with st.container(key="detail_summary"):
        price, patients, years, space = st.columns(4)
        price.metric("Asking price", money(practice.asking_price, missing="Undisclosed"))
        patients.metric(
            "Active patients",
            f"{practice.active_patients:,}" if practice.active_patients is not None else "Unknown",
        )
        years.metric(
            "Years operating",
            str(operating_years(practice)) if practice.founding_year is not None else "Unknown",
        )
        space.metric(
            "Space", f"{practice.sqft:,} sq ft" if practice.sqft is not None else "Unknown"
        )
        space.caption(room_summary(practice))
    _gap_summary(practice)
    save_controls_callback()

    overview, financials, premises, diligence, area, sources = st.tabs(
        [
            "Overview",
            "Financials",
            "Property & lease",
            "Due diligence",
            "Area & patients",
            "Sources",
        ]
    )
    with overview:
        _write(practice.description)
        st.markdown("**Practice history**")
        st.caption(
            f"Founded: {practice.founding_year if practice.founding_year is not None else 'Unknown'}"
        )
        if practice.history:
            for event in practice.history:
                _write("• " + event)
        else:
            st.caption("No ownership or transition history supplied.")
        st.markdown("**Availability evidence**")
        _write(practice.availability_evidence)
        st.caption(_source_reference(practice, practice.availability_source))
        st.caption("Availability recorded: " + practice.availability_date)
        _operations(practice)
    with financials:
        _financials(practice)
    with premises:
        _premises(practice)
    with diligence:
        st.markdown("**Seller legal disclosures**")
        _write(practice.legal_disclosures)
        st.markdown("**Independent legal research**")
        _write(practice.legal_research_status)
        st.markdown("**Missing information**")
        missing = missing_information(practice)
        if missing:
            for label in missing:
                _write("• " + label)
        else:
            st.caption(
                "Demo profile complete. All evidence is simulated; real transactions require independent verification."
            )
    with area:
        st.markdown("**Patient household income**")
        _evidence(practice, practice.patient_household_income)
        st.markdown("**Area household income**")
        st.caption(
            "Area residents do not establish the household income of this practice's patients."
        )
        _evidence(practice, practice.area_household_income)
        st.markdown("**Local crime statistics**")
        _evidence(practice, practice.crime)
    with sources:
        st.caption("Every source below is fictional and unverified.")
        for source in practice.sources:
            _write(f"**{source.label}**")
            st.caption(f"{source.kind} · {source.date} · Reference: {source.id}")
        if not practice.sources:
            st.caption("No source references supplied.")
    analysis_controls_callback()


def comparison_html(practices: list[Practice], filters: Filters) -> str:
    """Build an escaped semantic table with wrapped actual practice names."""
    if not practices:
        return ""
    rows = [
        ("Availability", lambda practice: practice.status),
        ("Asking price", lambda practice: money(practice.asking_price)),
        (
            "Budget fit",
            lambda practice: budget_fit(practice, filters.max_price, filters.max_price_inclusive),
        ),
        (
            "Reported annual revenue (not profit)",
            lambda practice: (
                money(practice.annual_revenue, missing="Unknown"),
                practice.revenue_period or "Reporting period unknown",
            ),
        ),
        (
            "Active patients",
            lambda practice: (
                f"{practice.active_patients:,}"
                if practice.active_patients is not None
                else "Unknown",
                practice.patient_period or "Reporting period unknown",
            ),
        ),
        (
            "Years operating",
            lambda practice: (
                str(operating_years(practice)) if practice.founding_year is not None else "Unknown"
            ),
        ),
        (
            "Space / clinical rooms",
            lambda practice: (
                (f"{practice.sqft:,} sq ft" if practice.sqft is not None else "Unknown size")
                + " · "
                + room_summary(practice)
            ),
        ),
        (
            "Modeled normalized EBITDA",
            lambda practice: (
                (
                    money(practice.financials.normalized_ebitda),
                    practice.financials.reporting_period + " · fictional, not audited",
                )
                if practice.financials
                else "Financial profile not supplied"
            ),
        ),
        (
            "Premises",
            lambda practice: (
                practice.premises.occupancy if practice.premises else "Profile not supplied"
            ),
        ),
        (
            "Annual lease cost (base + CAM)",
            lambda practice: (
                (
                    money(practice.premises.annual_base_rent + practice.premises.annual_cam)
                    if practice.premises.occupancy == "Leased"
                    else "Owner occupied · lease not applicable"
                )
                if practice.premises
                else "Profile not supplied"
            ),
        ),
        (
            "Separate property asking price",
            lambda practice: (
                (
                    money(practice.premises.property_asking_price)
                    if practice.premises.occupancy == "Owned"
                    else "Leased · no property offer"
                )
                if practice.premises
                else "Profile not supplied"
            ),
        ),
    ]

    def escape(value: object) -> str:
        return html.escape(str(value), quote=True)

    def cell(value) -> str:
        if isinstance(value, tuple):
            main, period = value
            return (
                '<td><span class="sera-comparison-value">'
                + escape(main)
                + "</span><small>"
                + escape(period)
                + "</small></td>"
            )
        return "<td>" + escape(value) + "</td>"

    headings = "".join(
        f'<th scope="col"><span>{escape(practice.name)}</span>'
        f"<small>{escape(practice.specialty)}<br>{escape(practice.city)}, {escape(practice.state)}</small></th>"
        for practice in practices
    )
    body = "".join(
        '<tr><th scope="row">'
        + escape(label)
        + "</th>"
        + "".join(cell(value(practice)) for practice in practices)
        + "</tr>"
        for label, value in rows
    )
    return (
        "<style>"
        + COMPARISON_CSS
        + "</style>"
        + (
            '<p class="sera-comparison-scrollhint">Scroll sideways to compare practices.</p>'
            '<div class="sera-comparison-wrap" tabindex="0" role="region" aria-label="Scrollable practice comparison">'
            f'<table class="sera-comparison" style="min-width:{150 + 190 * len(practices)}px" aria-label="Selected practice comparison">'
            "<caption>All evidence is fictional. Reporting periods appear beneath revenue and patient counts. Revenue is not profit; asking price is not total acquisition cost.</caption>"
            '<thead><tr><th scope="col">Recorded facts</th>'
            + headings
            + "</tr></thead><tbody>"
            + body
            + "</tbody></table></div>"
        )
    )


def render_comparison(practices: list[Practice], filters: Filters) -> None:
    """Show factual comparison; full records remain available in practice details."""
    if not practices:
        st.info("Choose practices from your saved list to compare their recorded facts.")
        return
    st.markdown(comparison_html(practices, filters), unsafe_allow_html=True)
