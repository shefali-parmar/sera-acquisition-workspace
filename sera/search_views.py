"""Search presentation and deterministic ordering for the existing Streamlit flow."""

from collections.abc import Iterable

import streamlit as st

from sera import ai
from sera.catalog import money
from sera.geography import distance_miles
from sera.models import SPECIALTIES, STATES, STATUSES, Filters, Practice
from sera.public_demo import DemoLimitError, reserve_ai_request
from sera.ranking import relevance_key
from sera.search_location import optional_origin, validate_distance_filters

sort_options = ("Relevance", "Distance", "Name A–Z", "Price low–high", "Price high–low")


def available_sort_options(filters: Filters) -> tuple[str, ...]:
    return tuple(
        option for option in sort_options if option != "Distance" or optional_origin(filters)
    )


def sorted_practices(
    records: Iterable[Practice], sort: str = "Relevance", filters: Filters | None = None
) -> list[Practice]:
    """Order already-filtered records without changing their membership or contents."""
    records = list(records)
    filters = filters or Filters()
    origin = optional_origin(filters)

    def miles(practice):
        return distance_miles(origin, practice.city, practice.state) if origin else None

    if sort == "Relevance":
        return sorted(
            records,
            key=lambda practice: relevance_key(
                practice, filters, distance=miles(practice), has_origin=origin is not None
            ),
        )
    if sort == "Distance":
        if origin is None:
            raise ValueError(
                "Add a ZIP code, city and state, or one state before sorting by distance."
            )

        def distance_key(practice):
            distance = miles(practice)
            return (distance is None, distance or 0, practice.name.casefold(), practice.id)

        return sorted(records, key=distance_key)
    if sort == "Name A–Z":
        return sorted(records, key=lambda practice: (practice.name.casefold(), practice.id))
    if sort not in sort_options:
        raise ValueError("Choose a supported sort order.")
    direction = 1 if sort == "Price low–high" else -1
    return sorted(
        records,
        key=lambda practice: (
            practice.asking_price is None,
            direction * practice.asking_price if practice.asking_price is not None else 0,
            practice.id,
        ),
    )


def _criteria_items(filters: Filters) -> list[tuple[str, str]]:
    locations = [STATES[state] for state in filters.states]
    if filters.city:
        locations.insert(0, filters.city)
    if filters.max_distance_miles is not None:
        origin = optional_origin(filters)
        locations = [
            f"Within {filters.max_distance_miles:g} miles of {origin.label if origin else filters.distance_origin}"
        ]
    price = (
        "No price cap"
        if filters.max_price is None
        else (("Up to " if filters.max_price_inclusive else "Under ") + money(filters.max_price))
    )
    availability = "; ".join(filters.statuses) or "No availability selected"
    items = [
        ("specialties", ", ".join(filters.specialties) or "Any specialty"),
        ("location", ", ".join(locations) or "Any location"),
        ("price", price),
        ("availability", availability),
        (
            "undisclosed",
            "Undisclosed prices included"
            if filters.include_undisclosed
            else "Undisclosed prices excluded",
        ),
    ]
    for key, value, suffix in (
        ("patients", filters.min_patients, "patients"),
        ("years", filters.min_years, "years operating"),
        ("space", filters.min_sqft, "sq ft"),
        ("operatories", filters.min_operatories, "operatories"),
    ):
        if value:
            items.append((key, f"{value:,}+ {suffix}"))
    if filters.distance_origin and filters.max_distance_miles is None:
        origin = optional_origin(filters)
        items.append(
            ("distance", "Distance from " + (origin.label if origin else filters.distance_origin))
        )
    if filters.keyword:
        items.append(("keyword", "Keyword: " + filters.keyword))
    return items


def criteria_summary(filters: Filters) -> str:
    """Summarize every applied constraint, including default evidence exclusions."""
    return " · ".join(label for _, label in _criteria_items(filters))


def catalog_scope(filters: Filters) -> str:
    if filters.statuses == STATUSES[:2]:
        availability = "Sale and succession opportunities; unknown availability excluded"
    elif filters.statuses:
        availability = "; ".join(filters.statuses)
        if "Availability unknown" not in filters.statuses:
            availability += "; unknown availability excluded"
    else:
        availability = "No availability selected"
    prices = (
        "undisclosed prices included"
        if filters.include_undisclosed
        else "undisclosed prices excluded"
    )
    return availability + "; " + prices + ". Fictional catalog."


def browse_identity(filters: Filters | None = None) -> tuple[str, str]:
    """Label the displayed catalog by applied state, independently of request drafts."""
    filters = filters if filters is not None else st.session_state.filters
    if not st.session_state.get("has_applied_search", False):
        heading = "Browse available practices"
    elif st.session_state.get("search_stage", "search") == "search":
        heading = "Current applied matches"
    else:
        heading = "Practices matching your criteria"
    return heading, catalog_scope(filters)


def _open_criteria() -> None:
    # Keep existing drafts; entering review never applies a search or removes criteria.
    st.session_state.search_stage = "review"


def applied_criteria_controls() -> None:
    """Compact edit actions; full constraints stay available in the criteria editor."""
    st.caption("APPLIED SEARCH CRITERIA")
    items = _criteria_items(st.session_state.filters)
    with st.container(key="criteria_chips"):
        columns = st.columns(5)
        for column, (key, label) in zip(columns[:4], items[:4]):
            compact = label if len(label) <= 42 else label[:39].rstrip() + "…"
            column.button(
                compact,
                key="criteria_chip_" + key,
                help=label + " · Edit criteria",
                on_click=_open_criteria,
                width="stretch",
            )
        columns[4].button(
            "All criteria", key="all_criteria", on_click=_open_criteria, width="stretch"
        )
    st.caption(catalog_scope(st.session_state.filters))
    change, edit = st.columns(2)
    if change.button("Change search", width="stretch"):
        st.session_state.search_stage = "search"
        st.rerun()
    if edit.button("Edit filters", width="stretch"):
        _open_criteria()
        st.rerun()


def search_controls() -> bool:
    """Keep request, criteria review and results as separate steps."""
    stage = st.session_state.get("search_stage", "search")
    step = {"search": 1, "review": 2, "results": 3}[stage]
    st.markdown(
        '<div class="sera-steps">'
        + "".join(
            f'<span class="{("active" if number == step else "")}">{number} · {label}</span>'
            for number, label in enumerate(("Describe", "Review criteria", "Explore matches"), 1)
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    if stage == "results":
        applied_criteria_controls()
        return False
    if stage == "search":
        with st.container(border=True):
            description = st.text_area(
                "Describe your ideal practice",
                height=85,
                placeholder="Dermatology in California, under $1.5 million…",
                key="search_description",
                value=st.session_state.get("description_draft", ""),
                max_chars=6000,
            )
            st.session_state.description_draft = description
            if not ai.configured():
                st.caption(
                    "Suggested criteria are unavailable right now. Choose Set filters manually, or browse the catalog below."
                )
            suggest, manual = st.columns(2)
            if suggest.button(
                "Suggest editable filters",
                type="primary",
                width="stretch",
                disabled=not ai.configured() or not description.strip(),
            ):
                try:
                    with st.spinner("Preparing your search criteria…"):
                        reserve_ai_request(st.session_state)
                        suggestion = ai.extract_filters(description)
                        validate_distance_filters(suggestion.filters)
                    st.session_state.suggestion = suggestion
                    st.session_state.suggestion_pending = True
                    st.session_state.filter_draft = suggestion.filters
                    st.session_state.filter_revision = (
                        st.session_state.get("filter_revision", 0) + 1
                    )
                    st.session_state.search_stage = "review"
                    st.rerun()
                except DemoLimitError as error:
                    st.info(str(error))
                except Exception:
                    st.error(
                        "Filter suggestion failed. Your request and applied filters are preserved. Retry or set filters manually."
                    )
            if manual.button("Set filters manually", width="stretch"):
                st.session_state.search_stage = "review"
                st.rerun()
            st.caption("Review every suggestion before applying it, or browse the catalog below.")
        if st.session_state.get("has_applied_search", False):
            applied_criteria_controls()
        return False
    st.subheader("Search criteria")
    if st.session_state.get("description_draft"):
        st.caption("YOUR REQUEST")
        st.write(st.session_state.description_draft)
    if st.button("Revise request"):
        st.session_state.search_stage = "search"
        st.rerun()
    suggestion = st.session_state.get("suggestion")
    pending = st.session_state.get("suggestion_pending", False)
    if pending and suggestion:
        st.info(
            "These suggestions are not applied yet. Review the criteria, then apply them to see matches."
        )
        if suggestion.preferences:
            st.write("Preferences: " + "; ".join(suggestion.preferences))
        if suggestion.unverifiable:
            st.warning("Cannot verify: " + "; ".join(suggestion.unverifiable))
        if suggestion.clarification:
            st.info(
                "Clarification: "
                + suggestion.clarification
                + " Resolve this in your request or criteria before applying."
            )
    defaults = st.session_state.get("filter_draft", st.session_state.filters)
    rev = str(st.session_state.get("filter_revision", 0))
    with st.container(border=True):
        left, right = st.columns(2)
        with left:
            specialties = st.multiselect(
                "Specialties", SPECIALTIES, default=defaults.specialties, key="sp" + rev
            )
            states = st.multiselect(
                "States · all 50 available",
                list(STATES),
                default=defaults.states,
                format_func=lambda x: STATES[x],
                key="states" + rev,
            )
            city = st.text_input("City", value=defaults.city, key="city" + rev)
            statuses = st.multiselect(
                "Availability", STATUSES, default=defaults.statuses, key="status" + rev
            )
        with right:
            price_enabled = st.checkbox(
                "Use a maximum asking price", value=defaults.max_price is not None, key="cap" + rev
            )
            price = st.number_input(
                "Maximum asking price ($)",
                min_value=0,
                value=defaults.max_price if defaults.max_price is not None else 0,
                step=50000,
                key="price" + rev,
                disabled=not price_enabled,
            )
            inclusive = st.checkbox(
                "Include practices exactly at the price cap",
                value=defaults.max_price_inclusive,
                key="inclusive" + rev,
                disabled=not price_enabled,
                help="Clear for strictly under the maximum price; select for up to and including it.",
            )
            undisclosed = st.checkbox(
                "Include undisclosed prices · budget unverified",
                value=defaults.include_undisclosed,
                key="unknown" + rev,
            )
        with st.expander("More criteria · patients, years and space"):
            keyword = st.text_input(
                "Keyword · name, specialty, description",
                value=defaults.keyword,
                key="keyword" + rev,
            )
            minimums = {}
            first, second = st.columns(2)
            for index, (field, label, increment, widget) in enumerate(
                (
                    ("min_patients", "Minimum active patients", 100, "patients"),
                    ("min_years", "Minimum years operating", 1, "years"),
                    ("min_sqft", "Minimum square feet", 100, "sqft"),
                    ("min_operatories", "Minimum operatories", 1, "ops"),
                )
            ):
                with first if index % 2 == 0 else second:
                    minimums[field] = st.number_input(
                        label,
                        min_value=0,
                        value=getattr(defaults, field),
                        step=increment,
                        key=widget + rev,
                    )
            st.caption("Missing evidence cannot satisfy a positive minimum.")
        with st.expander(
            "Distance (optional)",
            expanded=bool(defaults.distance_origin or defaults.max_distance_miles),
        ):
            distance_origin = st.text_input(
                "Distance from · ZIP, city, or state",
                value=defaults.distance_origin,
                key="distance_origin" + rev,
                max_chars=120,
                placeholder="95814, Sacramento, CA, or California",
                help="A ZIP takes priority. Otherwise use a city center or state center. Leave blank to use your City and single selected State.",
            )
            radius_enabled = st.checkbox(
                "Limit distance",
                value=defaults.max_distance_miles is not None,
                key="radius_enabled" + rev,
            )
            radius = st.number_input(
                "Maximum distance (miles)",
                min_value=1.0,
                max_value=10000.0,
                value=float(defaults.max_distance_miles or 50),
                step=25.0,
                key="radius" + rev,
                disabled=not radius_enabled,
            )
            st.caption(
                "Approximate straight-line miles from the ZIP, city, or state center to each practice's city center. Not driving distance."
            )
            if radius_enabled:
                st.info(
                    "The radius replaces exact City and State restrictions. All other criteria still apply."
                )
        draft = Filters(
            specialties=specialties,
            states=states,
            city=city,
            max_price=price if price_enabled else None,
            max_price_inclusive=inclusive,
            statuses=statuses,
            keyword=keyword,
            include_undisclosed=undisclosed,
            distance_origin=distance_origin,
            max_distance_miles=radius if radius_enabled else None,
            **minimums,
        )
        valid_distance = True
        try:
            validate_distance_filters(draft)
        except ValueError as error:
            valid_distance = False
            st.error(str(error))
        st.session_state.filter_draft = draft
        if draft != st.session_state.filters or pending:
            st.caption(
                "You have unapplied changes. Your current search stays unchanged until you apply them."
            )
        apply, revert, reset = st.columns(3)
        if apply.button(
            "Apply filters", type="primary", width="stretch", disabled=not valid_distance
        ):
            st.session_state.filters = draft
            st.session_state.has_applied_search = True
            st.session_state.result_page = 0
            if pending and suggestion:
                st.session_state.search_preferences = suggestion.preferences
                st.session_state.search_unverifiable = suggestion.unverifiable
            st.session_state.suggestion_pending = False
            st.session_state.search_stage = "results"
            st.rerun()
        if revert.button(
            "Discard unapplied changes",
            disabled=draft == st.session_state.filters and not pending,
            width="stretch",
        ):
            st.session_state.filter_draft = st.session_state.filters
            st.session_state.suggestion_pending = False
            st.session_state.filter_revision = st.session_state.get("filter_revision", 0) + 1
            st.session_state.search_stage = "results"
            st.rerun()
        if reset.button("Reset all filters", width="stretch"):
            st.session_state.filters = Filters()
            st.session_state.has_applied_search = False
            st.session_state.result_page = 0
            st.session_state.filter_draft = Filters()
            st.session_state.suggestion = None
            st.session_state.suggestion_pending = False
            st.session_state.search_preferences = []
            st.session_state.search_unverifiable = []
            st.session_state.filter_revision = st.session_state.get("filter_revision", 0) + 1
            st.rerun()
    return True
