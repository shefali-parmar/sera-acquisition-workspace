"""SERA's three screens. Run with: streamlit run app.py."""

import hashlib
import json
import re
from html import escape

import streamlit as st
from pydantic import ValidationError

from sera import ai
from sera.catalog import (
    budget_fit,
    load_practices,
    money,
    operating_years,
    search,
)
from sera.design import APP_CSS
from sera.models import Filters, Practice, SavedStore
from sera.practice_views import missing_information, render_practice_details
from sera.public_demo import DemoLimitError, public_demo_enabled, reserve_ai_request
from sera.search_views import (
    browse_identity,
    criteria_summary,
    search_controls,
    sort_options,
    sorted_practices,
)
from sera.storage import ListStorage, SessionListStorage, StorageError
from sera.workspace_views import WorkspaceCallbacks, render_assistant, render_shortlists


def effective_goals() -> str:
    """Combine buyer goals, visible preferences, and applied filters for the agent."""
    return "\n".join(
        [
            st.session_state.goals,
            "Search preferences: " + "; ".join(st.session_state.get("search_preferences", [])),
            "Unverifiable requirements: "
            + "; ".join(st.session_state.get("search_unverifiable", [])),
            "Applied filters: " + json.dumps(st.session_state.filters.model_dump()),
        ]
    )


def guarded_investigate(*args, **kwargs):
    """Reserve a public-demo request before invoking the assistant."""
    reserve_ai_request(st.session_state)
    return ai.investigate(*args, **kwargs)


def run_analysis(key: str, question: str, ids: list[str], signature: tuple) -> None:
    """Replace a snapshot only after success, preserving previous work on failure."""
    try:
        with st.spinner("SERA is retrieving evidence and preparing an assessment…"):
            context = effective_goals()
            result = guarded_investigate(question, context, required_ids=ids)
        st.session_state.analyses[key] = (result, signature, context, list(ids))
    except DemoLimitError as error:
        st.info(str(error))
    except Exception:
        st.error(
            "Analysis could not be completed. Your inputs and any previous assessment are preserved. Retry, or ask the operator to check AI provider or local model configuration."
        )


def buyer_answer_markdown(answer: str) -> str:
    """Keep dollar-denominated amounts literal in Streamlit's Markdown renderer."""
    for practice in load_practices():
        # Preserve source references; record IDs are an internal retrieval detail.
        answer = re.sub(
            rf"\b{re.escape(practice.id)}\b(?!-S\d+)(?:\s*[—–]\s*{re.escape(practice.name)})?",
            practice.name,
            answer,
        )
    answer = answer.replace("Practice IDs", "Practices").replace("Practice ID", "Practice")
    return re.sub(r"(?<!\\)\$(?=\d)", r"\\$", answer)


def show_assessment_notice(result: ai.Investigation) -> None:
    """Explain a limited answer without exposing internal correction instructions."""
    if result.get("status") == "facts_only":
        st.warning(
            "SERA could not support a complete assessment. The recorded facts remain available. Try again or refine your question."
        )


def show_analysis(key: str, signature: tuple) -> None:
    """Show the stored assessment and flag changed goals or candidate membership."""
    if key not in st.session_state.analyses:
        return
    result, old, context, ids = st.session_state.analyses[key]
    st.caption(
        "Assessment based on fictional prototype data. Snapshot of buyer goals and selected practices."
    )
    if old != signature:
        st.warning(
            "This snapshot is out of date: buyer goals or list membership changed. Generate again."
        )
    show_assessment_notice(result)
    st.markdown(buyer_answer_markdown(result["answer"]))
    show_sources(result)
    if st.button(
        "Ask a follow-up about this assessment",
        key="follow_up_" + key,
    ):
        continue_assessment(result, context, ids)
        st.session_state.pop("requested_page", None)
        st.switch_page("screens/ask_sera.py")


def continue_assessment(result: ai.Investigation, context: str, ids: list[str]) -> None:
    """Move a successful snapshot into chat; later turns retrieve its evidence again."""
    st.session_state.chat_context = context
    st.session_state.chat_required_ids = list(ids)
    st.session_state.history = result["history"]
    # Internal model history includes request instructions; buyers see the saved answer.
    st.session_state.chat = [{"role": "assistant", "content": result["answer"]}]
    st.session_state.continuing_assessment = True
    st.session_state.last_trace = result
    st.session_state.workspace = "Acquisition assistant"
    st.session_state.requested_page = "screens/ask_sera.py"
    st.session_state.pop("assistant_question", None)
    st.session_state.pop("assistant_question_draft", None)
    st.session_state.pop("assistant_task_draft", None)
    st.session_state.pop("assistant_clear_composer", None)


def show_sources(result: ai.Investigation) -> None:
    """Show readable evidence attribution alongside buyer-facing assessments."""
    sources = result.get("sources", [])
    if not sources:
        return
    with st.expander("Source details · fictional evidence"):
        seen = set()
        for source in sources:
            reference = source.get("id", "Unknown reference")
            if reference in seen:
                continue
            seen.add(reference)
            st.write(source.get("label", "Evidence source"))
            st.caption(
                f"{source.get('kind', 'Source type unknown')} · "
                f"{source.get('date', 'Date unknown')} · Reference: {reference}"
            )


def storage_action(operation) -> bool:
    """Keep list input and existing records visible when a write fails."""
    try:
        operation()
        return True
    except StorageError as error:
        st.error(
            f"Saved-list changes could not be saved: {error} Your existing lists are preserved."
        )
        return False
    except (OSError, ValueError, StopIteration):
        st.error(
            "Saved-list changes could not be saved. Your existing lists are preserved. Check the list name, reload if another window changed it, or ask the operator to check storage."
        )
        return False


def practice_label(practice: Practice) -> str:
    return f"{practice.name} · {practice.city}, {practice.state}"


def content_revision(value) -> str:
    """Invalidate edit widgets whenever the persisted contents change."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]


def save_controls(
    practice: Practice, storage: ListStorage, saved: SavedStore, *, key_prefix: str = "save"
) -> None:
    """A practice can belong to several lists; commit membership in one write."""
    if storage is None:
        st.caption("Saving is unavailable while the saved-list file needs recovery.")
        return
    options = {x.id: x.name for x in saved.lists}
    if options:
        chosen = st.multiselect(
            "Save to lists",
            list(options),
            default=[x.id for x in saved.lists if practice.id in x.practice_ids],
            format_func=lambda x: options[x],
            key=f"{key_prefix}_save_{practice.id}_{content_revision(saved.model_dump())}",
        )
        if st.button("Update saved lists", key=f"{key_prefix}_update_{practice.id}"):
            if storage_action(lambda: storage.set_memberships(practice.id, chosen)):
                st.session_state.list_notice = "Saved-list membership updated."
                st.rerun()

    def create_list_and_save() -> None:
        name = st.text_input(
            "New list name", max_chars=80, key=f"{key_prefix}_new_list_for_{practice.id}"
        )
        if st.button("Create list & save", key=f"{key_prefix}_create_save_{practice.id}"):
            if not name.strip():
                st.error("Enter a list name.")
                return

            def create_with_practice():
                st.session_state.selected_list = storage.create(name, practice_ids=[practice.id])

            if storage_action(create_with_practice):
                st.session_state.list_notice = "List created and practice saved. Open Shortlists to compare or export your candidates."
                st.rerun()

    if not options:
        st.caption("Create your first named list and save this practice in one step.")
        create_list_and_save()
    else:
        with st.expander("Create another list for this practice"):
            create_list_and_save()


@st.dialog("Practice details", width="large")
def details(practice: Practice, storage: ListStorage, saved: SavedStore) -> None:
    """Show an organized record with saving and optional analysis as clear actions."""

    def save_action():
        with st.popover("Save to a list", width="stretch"):
            save_controls(practice, storage, saved, key_prefix="dialog")

    def analysis_action():
        with st.expander("Ask SERA about this practice"):
            signature = (effective_goals(), practice.id)
            if st.button(
                "Generate acquisition brief",
                disabled=not ai.configured(),
                key=f"brief_{practice.id}",
            ):
                run_analysis(
                    practice.id,
                    f"Generate a complete acquisition brief for {practice.id}. Retrieve its details first.",
                    [practice.id],
                    signature,
                )
            show_analysis(practice.id, signature)

    render_practice_details(practice, save_action, analysis_action)


def card(
    practice: Practice,
    storage: ListStorage,
    saved: SavedStore,
    *,
    key_prefix: str = "explore",
    comparison_selected: bool | None = None,
    on_compare_change=None,
) -> None:
    """A compact evidence summary with independent viewing and saving actions."""
    years = operating_years(practice)
    patients = (
        f"{practice.active_patients:,}" if practice.active_patients is not None else "Unknown"
    )
    years_text = f"{years} years operating" if years is not None else "Operating years unknown"
    fit = budget_fit(
        practice, st.session_state.filters.max_price, st.session_state.filters.max_price_inclusive
    )
    fit_text = (
        f'<div class="sera-card-fit">{escape(fit)}</div>'
        if st.session_state.filters.max_price is not None
        else ""
    )
    memberships = [item for item in saved.lists if practice.id in item.practice_ids]
    gaps = missing_information(practice)
    # Keep the complete gap list in the profile; cards surface two concrete unknowns.
    priority_gaps = []
    if practice.asking_price is None:
        priority_gaps.append("Price not supplied")
    if practice.annual_revenue is None:
        priority_gaps.append("Revenue not supplied")
    if re.match(r"\s*unknown\b", practice.legal_research_status, re.I):
        priority_gaps.append("Legal research unknown")
    if not priority_gaps:
        priority_gaps = [label + " not supplied" for label in gaps[:2]]
    gap_text = " · ".join(priority_gaps[:2])
    saved_text = (
        f"Saved in {len(memberships)} {'list' if len(memberships) == 1 else 'lists'}"
        if memberships
        else ""
    )
    with st.container(border=True, key=f"practice_card_{key_prefix}_{practice.id}"):
        st.markdown(
            f'<div class="sera-card"><div class="sera-card-meta">{escape(practice.specialty)} · {escape(practice.city)}, {escape(practice.state)}</div>'
            f'<h3>{escape(practice.name)}</h3><span class="sera-status">{escape(practice.status)}</span>'
            f'<div class="sera-card-price">{escape(money(practice.asking_price))}</div>{fit_text}'
            f'<div class="sera-card-facts">{patients} active patients<br>{years_text}</div>'
            + (
                f'<div class="sera-card-gaps">Evidence gaps: {escape(gap_text)}</div>'
                if gap_text
                else ""
            )
            + (f'<div class="sera-card-saved">{escape(saved_text)}</div>' if saved_text else "")
            + "</div>",
            unsafe_allow_html=True,
        )
        view, save = st.columns([3, 2])
        with view:
            if st.button(
                "View practice", key=f"details_{practice.id}", width="stretch", type="primary"
            ):
                details(practice, storage, saved)
        with save:
            with st.popover(
                "Saved" if memberships else "Save", width="stretch", disabled=storage is None
            ):
                save_controls(practice, storage, saved, key_prefix=key_prefix)
        if comparison_selected is not None:
            checkbox_key = f"{key_prefix}_compare_{practice.id}"
            st.session_state[checkbox_key] = comparison_selected

            def select_candidate():
                selected = bool(st.session_state[checkbox_key])
                accepted = on_compare_change(practice.id, selected)
                if accepted is not None:
                    st.session_state[checkbox_key] = bool(accepted)

            st.checkbox("Select for comparison", key=checkbox_key, on_change=select_candidate)


def explore_practices(records: list[Practice], storage: ListStorage, saved: SavedStore) -> None:
    """Browse a small grid after describing and reviewing a search."""
    if search_controls():
        return
    if st.session_state.get("search_preferences"):
        st.caption("Preferences: " + "; ".join(st.session_state.search_preferences))
    if st.session_state.get("search_unverifiable"):
        st.warning(
            "Your request includes requirements this dataset cannot verify: "
            + "; ".join(st.session_state.search_unverifiable)
        )
    heading, caption = browse_identity(st.session_state.filters)
    st.subheader(heading)
    if st.session_state.get("search_stage", "search") != "results":
        st.caption(caption)
    current_sort = st.session_state.get("result_sort", sort_options[0])
    st.session_state.result_sort = current_sort
    st.session_state._result_sort = current_sort

    def change_sort():
        st.session_state.result_sort = st.session_state._result_sort

    st.selectbox("Sort practices", sort_options, key="_result_sort", on_change=change_sort)
    results = sorted_practices(
        search(records, st.session_state.filters), st.session_state.result_sort
    )
    signature = (
        st.session_state.filters.model_dump_json(),
        st.session_state.result_sort,
        tuple(practice.id for practice in results),
    )
    if st.session_state.get("results_signature") != signature:
        st.session_state.results_signature = signature
        st.session_state.result_page = 0
    page = st.session_state.get("result_page", 0)
    page_size = 6
    pages = max(1, (len(results) + page_size - 1) // page_size)
    page = min(page, pages - 1)
    if not results:
        st.info(
            "No fictional records match these filters. Your selected location has been preserved. Try editing filters; this dataset does not cover every state or city."
        )
        if st.button("Edit filters", key="empty_edit_filters"):
            st.session_state.search_stage = "review"
            st.rerun()
        return
    st.caption(
        f"Showing {page * page_size + 1}–{min((page + 1) * page_size, len(results))} of {len(results)} · Fictional practices"
    )
    visible = results[page * page_size : (page + 1) * page_size]
    with st.container(key="practice_grid"):
        for column, practice in zip(st.columns(len(visible)), visible):
            with column:
                card(practice, storage, saved, key_prefix="explore")
    if pages > 1:
        previous, count, following = st.columns([1, 2, 1])
        if previous.button("Previous", disabled=page == 0, width="stretch"):
            st.session_state.result_page = page - 1
            st.rerun()
        count.caption(f"Page {page + 1} of {pages}")
        if following.button("Next", disabled=page >= pages - 1, width="stretch"):
            st.session_state.result_page = page + 1
            st.rerun()


def workspace_callbacks() -> WorkspaceCallbacks:
    return WorkspaceCallbacks(
        card=card,
        effective_goals=effective_goals,
        criteria_summary=criteria_summary,
        storage_action=storage_action,
        run_analysis=run_analysis,
        show_analysis=show_analysis,
        show_sources=show_sources,
        show_assessment_notice=show_assessment_notice,
        buyer_answer_markdown=buyer_answer_markdown,
        ai_configured=ai.configured,
        investigate=guarded_investigate,
    )


def render_workspace(section: str) -> None:
    """Render the registered native page using this rerun's current records."""
    records, storage, saved = st.session_state.runtime_records
    by_id = {practice.id: practice for practice in records}
    st.session_state.workspace = section
    headings = {
        "Explore practices": "Find your next practice.",
        "Saved lists": "Your shortlists",
        "Acquisition assistant": "Ask SERA",
    }
    st.title(headings[section])
    st.caption(
        "Evaluate practices, compare leasing or buying a property, and plan your due diligence. "
        "Ask a general question or add practices for a tailored review."
        if section == "Acquisition assistant"
        else "Demo catalog · Fictional practices and evidence. No live marketplace search."
    )
    if section == "Explore practices":
        explore_practices(records, storage, saved)
    elif section == "Saved lists":
        render_shortlists(by_id, storage, saved, workspace_callbacks())
    else:
        render_assistant(by_id, workspace_callbacks(), saved=saved)


def main() -> None:
    st.set_page_config(page_title="SERA · Practice acquisitions", page_icon="🌿", layout="wide")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    try:
        records = load_practices()
    except (OSError, ValidationError, ValueError):
        st.error(
            "The demo practice catalog could not be loaded. Restore a valid catalog, then reload SERA."
        )
        st.stop()
    storage = SessionListStorage(st.session_state) if public_demo_enabled() else ListStorage()
    try:
        saved = storage.load()
    except (OSError, ValidationError, ValueError):
        st.error(
            "Saved-list data needs recovery. The existing file is preserved; browsing remains available."
        )
        saved = SavedStore()
        storage = None
    for key, value in [
        ("filters", Filters()),
        ("history", []),
        ("chat", []),
        ("analyses", {}),
        ("goals", ""),
    ]:
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state.runtime_records = (records, storage, saved)
    pages = [
        st.Page("screens/explore.py", title="Explore", icon=":material/search:", default=True),
        st.Page(
            "screens/shortlists.py",
            title="Shortlists",
            icon=":material/bookmarks:",
            url_path="shortlists",
        ),
        st.Page(
            "screens/ask_sera.py", title="Ask SERA", icon=":material/chat:", url_path="ask-sera"
        ),
    ]
    page = st.navigation(pages, position="hidden")
    requested = st.session_state.pop("requested_page", None)
    if requested:
        st.switch_page(requested)
    with st.sidebar:
        st.markdown('<div class="sera-brand">SERA</div>', unsafe_allow_html=True)
        st.caption("Your practice acquisition workspace")
        for entry in pages:
            st.page_link(entry, label=entry.title, icon=entry.icon, width="stretch")
        st.divider()
        st.text_area(
            "Acquisition priorities (optional)",
            key="goals",
            placeholder="Transition support, ownership plans, and other priorities",
            max_chars=4000,
        )
        st.caption("Guides assessments; does not change search matches.")
        st.divider()
        st.caption(f"Demo workspace · {len(records)} fictional practices")
        if public_demo_enabled():
            st.caption(
                "Your shortlists stay private to this visit. Export them before closing or reloading. "
                "AI usage is limited for this public demo."
            )
        st.caption(
            "AI assessments configured"
            if ai.configured()
            else "AI assessments unavailable · browsing and saving remain available"
        )
    if notice := st.session_state.pop("list_notice", None):
        st.success(notice)
    page.run()


if __name__ == "__main__":
    main()
