"""Shortlist and assistant screens with injected application actions."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from sera.exports import build_list_export, export_csv, export_filename, export_json
from sera.ma_workspace import deal_notes, deal_tasks
from sera.models import Filters, Practice, SavedList, SavedStore
from sera.practice_views import render_comparison
from sera.public_demo import DemoLimitError
from sera.storage import ListStorage


@dataclass(frozen=True)
class WorkspaceCallbacks:
    """Application actions stay in app.py; these views own presentation/session state."""

    card: Callable[..., None]
    effective_goals: Callable[[], str]
    criteria_summary: Callable[[Filters], str]
    storage_action: Callable[[Callable], bool]
    run_analysis: Callable[[str, str, list[str], tuple], None]
    show_analysis: Callable[[str, tuple], None]
    show_sources: Callable[[dict], None]
    show_assessment_notice: Callable[[dict], None]
    buyer_answer_markdown: Callable[[str], str]
    ai_configured: Callable[[], bool]
    investigate: Callable[..., dict]
    resolve_candidates: Callable[[str, list, list[str]], list[str]] | None = None


def _revision(item: SavedList) -> str:
    return hashlib.sha256(item.model_dump_json().encode()).hexdigest()[:12]


def _label(practice: Practice) -> str:
    return f"{practice.name} · {practice.city}, {practice.state}"


def _explore() -> None:
    st.session_state.workspace = "Explore practices"
    st.session_state.requested_page = "screens/explore.py"


def _create_list(storage: ListStorage, callbacks: WorkspaceCallbacks, *, scope: str) -> None:
    with st.form(f"create_list_{scope}"):
        name = st.text_input("New list name", max_chars=80, key=f"new_list_name_{scope}")
        if st.form_submit_button("Create list"):
            if not name.strip():
                st.error("Enter a list name.")
            else:
                created = []
                if callbacks.storage_action(lambda: created.append(storage.create(name))):
                    # Apply before rendering the selector on the next full run.
                    st.session_state.shortlist_pending_list = created[0]
                    st.session_state.list_notice = (
                        "List created. Save practices from Explore practices."
                    )
                    st.rerun()


def _dismiss_delete() -> None:
    st.session_state.pop("shortlist_delete_snapshot", None)


@st.dialog("Delete shortlist", on_dismiss=_dismiss_delete)
def _confirm_delete(item: SavedList, storage: ListStorage, callbacks: WorkspaceCallbacks) -> None:
    st.write(f"Delete “{item.name}” and its {len(item.practice_ids)} saved memberships?")
    st.caption("This permanently deletes the list. The fictional practice catalog is preserved.")
    delete, cancel = st.columns(2)
    if delete.button("Delete permanently", type="primary", key=f"confirm_delete_{item.id}"):
        if callbacks.storage_action(
            lambda: storage.update(
                item.id,
                delete=True,
                expected_name=item.name,
                expected_practice_ids=list(item.practice_ids),
            )
        ):
            st.session_state.list_notice = "List deleted."
            _dismiss_delete()
            st.rerun()
    if cancel.button("Cancel", key=f"cancel_delete_{item.id}"):
        _dismiss_delete()
        st.rerun()


def _list_actions(
    item: SavedList, by_id: dict[str, Practice], storage: ListStorage, callbacks: WorkspaceCallbacks
) -> None:
    revision = _revision(item)
    with st.popover("List actions", width="stretch"):
        with st.expander("Rename list"):
            with st.form(f"rename_list_{item.id}_{revision}"):
                name = st.text_input(
                    "List name",
                    value=item.name,
                    max_chars=80,
                    key=f"list_name_{item.id}_{revision}",
                )
                if st.form_submit_button("Save name"):
                    if not name.strip():
                        st.error("Enter a list name.")
                    elif callbacks.storage_action(
                        lambda: storage.update(
                            item.id,
                            name=name,
                            expected_name=item.name,
                            expected_practice_ids=list(item.practice_ids),
                        )
                    ):
                        st.session_state.list_notice = "List name saved."
                        st.rerun()
        with st.expander("Edit membership"):
            with st.form(f"edit_membership_{item.id}_{revision}"):
                members = st.multiselect(
                    "Practices in this list · remove or add candidates",
                    list(by_id),
                    default=[pid for pid in item.practice_ids if pid in by_id],
                    format_func=lambda pid: _label(by_id[pid]),
                    key=f"membership_{item.id}_{revision}",
                )
                unavailable = [pid for pid in item.practice_ids if pid not in by_id]
                if unavailable:
                    st.caption(f"{len(unavailable)} unavailable saved records will be retained.")
                if st.form_submit_button("Save list changes") and callbacks.storage_action(
                    lambda: storage.update(
                        item.id,
                        practice_ids=members + unavailable,
                        expected_name=item.name,
                        expected_practice_ids=list(item.practice_ids),
                    )
                ):
                    st.session_state.list_notice = "List membership saved."
                    st.rerun()
        with st.expander("Export list"):
            export = build_list_export(
                item,
                by_id,
                filters=st.session_state.filters,
                buyer_goals=callbacks.effective_goals(),
            )
            st.caption(
                "Exports include the entire list and recorded evidence, including unavailable IDs. "
                "Saved practices may be outside your current filters."
            )
            st.download_button(
                "Export list as JSON",
                export_json(export),
                file_name=export_filename(item.name, "json"),
                mime="application/json",
                key=f"list_json_{item.id}",
            )
            st.download_button(
                "Export list as CSV",
                export_csv(export),
                file_name=export_filename(item.name, "csv"),
                mime="text/csv",
                key=f"list_csv_{item.id}",
            )
        with st.expander("Create another list"):
            _create_list(storage, callbacks, scope="another")
        st.divider()
        if st.button("Delete list", key=f"delete_{item.id}"):
            st.session_state.shortlist_delete_snapshot = item.model_dump()


def _selection(list_id: str, candidates: list[str]) -> list[str]:
    selections = dict(st.session_state.get("shortlist_comparison_selection", {}))
    selected = list(dict.fromkeys(pid for pid in selections.get(list_id, []) if pid in candidates))[
        :3
    ]
    selections[list_id] = selected
    st.session_state.shortlist_comparison_selection = selections
    return selected


def _set_selection(list_id: str, candidates: list[str], practice_id: str, enabled: bool) -> bool:
    """Return the accepted checkbox value so a rejected fourth selection is reset."""
    selected = _selection(list_id, candidates)
    if enabled and practice_id not in selected:
        if practice_id not in candidates or len(selected) >= 3:
            st.session_state.shortlist_selection_notice = (
                "Compare up to three practices. Deselect one to choose another."
            )
            return False
        selected.append(practice_id)
    elif not enabled:
        selected = [pid for pid in selected if pid != practice_id]
    st.session_state.shortlist_comparison_selection = {
        **st.session_state.shortlist_comparison_selection,
        list_id: selected,
    }
    return enabled


def _clear_selection(list_id: str) -> None:
    selections = dict(st.session_state.get("shortlist_comparison_selection", {}))
    selections[list_id] = []
    st.session_state.shortlist_comparison_selection = selections
    # Card widget keys are owned by the app; a new revision resets their defaults.
    revisions = dict(st.session_state.get("shortlist_selection_revision", {}))
    revisions[list_id] = revisions.get(list_id, 0) + 1
    st.session_state.shortlist_selection_revision = revisions


def _choose_list() -> None:
    st.session_state.selected_list = st.session_state._selected_list


def render_shortlists(
    by_id: dict[str, Practice],
    storage: ListStorage | None,
    saved: SavedStore,
    callbacks: WorkspaceCallbacks,
) -> None:
    """Put saved candidates first; comparison selection never mutates a saved list."""
    if storage is None:
        st.info(
            "Lists are temporarily unavailable. Your saved file is preserved; browsing and the assistant remain available."
        )
        return
    if not saved.lists:
        st.info(
            "Your shortlist starts with a practice. Explore matches and choose Save to create your first list."
        )
        st.button(
            "Explore practices", on_click=_explore, type="primary", key="empty_shortlist_explore"
        )
        with st.popover("Create an empty list"):
            _create_list(storage, callbacks, scope="first")
        return
    lists_by_id = {item.id: item for item in saved.lists}
    pending = st.session_state.pop("shortlist_pending_list", None)
    if pending in lists_by_id:
        st.session_state.selected_list = pending
    if st.session_state.get("selected_list") not in lists_by_id:
        st.session_state.selected_list = next(iter(lists_by_id))
    # Canonical selection survives page changes; Streamlit may clean up hidden widgets.
    st.session_state._selected_list = st.session_state.selected_list
    selector, actions = st.columns([3, 1])
    with selector:
        selected_list = st.selectbox(
            "Choose list",
            list(lists_by_id),
            format_func=lambda pid: lists_by_id[pid].name,
            key="_selected_list",
            on_change=_choose_list,
        )
    item = lists_by_id[selected_list]
    with actions:
        _list_actions(item, by_id, storage, callbacks)
    candidates = [pid for pid in item.practice_ids if pid in by_id]
    unavailable = [pid for pid in item.practice_ids if pid not in by_id]
    chosen = _selection(item.id, candidates)
    st.caption(f"{len(candidates)} available candidates · {len(chosen)} selected for comparison")
    if unavailable:
        st.warning(
            f"{len(unavailable)} saved records are unavailable in this catalog. Their IDs remain in your list and exports."
        )
    if notice := st.session_state.pop("shortlist_selection_notice", None):
        st.warning(notice)
    if not candidates:
        st.info(
            "This list has no available practices yet. Save candidates from Explore practices, or use List actions to edit membership."
        )
        st.button("Explore practices", on_click=_explore, key="empty_list_explore")
    else:
        selection_revision = st.session_state.get("shortlist_selection_revision", {}).get(
            item.id, 0
        )
        with st.container(key="saved_grid"):
            for column, pid in zip(st.columns(len(candidates)), candidates):
                with column:
                    callbacks.card(
                        by_id[pid],
                        storage,
                        saved,
                        key_prefix=f"shortlist_{item.id}_{selection_revision}",
                        comparison_selected=pid in chosen,
                        on_compare_change=lambda pid, selected: _set_selection(
                            item.id, candidates, pid, selected
                        ),
                    )
    compare, clear = st.columns([3, 1])
    if compare.button(
        "Compare selected",
        disabled=len(chosen) < 2,
        type="primary",
        key=f"compare_selected_{item.id}",
    ):
        visible = dict(st.session_state.get("shortlist_comparison_open", {}))
        visible[item.id] = tuple(chosen)
        st.session_state.shortlist_comparison_open = visible
    clear.button(
        "Clear selection",
        disabled=not chosen,
        key=f"clear_comparison_{item.id}",
        on_click=_clear_selection,
        args=(item.id,),
    )
    comparison_open = st.session_state.get("shortlist_comparison_open", {}).get(item.id)
    if len(chosen) >= 2 and comparison_open == tuple(chosen):
        st.subheader("Selected practice comparison")
        render_comparison([by_id[pid] for pid in chosen], st.session_state.filters)
        st.caption(
            "Recorded facts only. Asking price is not total acquisition cost; revenue is not profit."
        )
        signature = (
            callbacks.effective_goals(),
            tuple(item.practice_ids),
            tuple(chosen),
            st.session_state.filters.max_price,
        )
        if st.button(
            "Compare with SERA",
            disabled=not callbacks.ai_configured(),
            key=f"ai_comparison_{item.id}",
        ):
            callbacks.run_analysis(
                "comparison_" + item.id,
                f"Compare every selected practice {chosen}. Retrieve all details. Budget cap: {st.session_state.filters.max_price}. Provide comparison advantages, concerns, missing information and tradeoffs; recommend up to three.",
                chosen,
                signature,
            )
    elif comparison_open:
        st.caption("Selection changed. Choose Compare selected to review the current candidates.")
    signature = (
        callbacks.effective_goals(),
        tuple(item.practice_ids),
        tuple(chosen),
        st.session_state.filters.max_price,
    )
    callbacks.show_analysis("comparison_" + item.id, signature)

    if pending_delete := st.session_state.get("shortlist_delete_snapshot"):
        _confirm_delete(SavedList.model_validate(pending_delete), storage, callbacks)


def _new_conversation() -> None:
    st.session_state.history = []
    st.session_state.chat = []
    for key in (
        "last_trace",
        "chat_context",
        "chat_required_ids",
        "continuing_assessment",
        "assistant_question",
        "assistant_question_draft",
        "assistant_clear_composer",
        "assistant_task_draft",
        "assistant_target_notice",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith("ma_target_choices_") or key == "ma_target_source":
            st.session_state.pop(key, None)


def _populate_question(question: str) -> None:
    st.session_state.assistant_question = question
    st.session_state.assistant_question_draft = question
    st.session_state.assistant_task_draft = question


def _remember_question() -> None:
    st.session_state.assistant_question_draft = st.session_state.assistant_question


def _use_targets(chosen: list[str]) -> None:
    """Commit a scope without calling AI or changing search/list state."""
    old = st.session_state.get("chat_required_ids", [])
    if list(chosen) != old:
        question = st.session_state.get("assistant_question", "")
        if question and question == st.session_state.get("assistant_task_draft"):
            st.session_state.assistant_question = ""
            st.session_state.assistant_question_draft = ""
        elif question.strip():
            st.session_state.assistant_target_notice = (
                "Your draft was kept. Check any practice names before sending."
            )
        st.session_state.pop("assistant_task_draft", None)
    st.session_state.chat_required_ids = list(chosen)


def _target_picker(
    by_id: dict[str, Practice], required_ids: list[str], saved: SavedStore | None, locked: bool
) -> None:
    with st.popover("Add practices", width="content", icon=":material/add:"):
        if locked:
            st.caption("Start a new conversation to choose different targets.")
            return
        st.caption("Choose up to three targets. This does not change your search or shortlists.")
        st.caption("Applying replaces the current target selection with the choices below.")
        lists = {item.id: item for item in saved.lists} if saved else {}
        if st.session_state.get("ma_target_source") not in {"catalog", *lists}:
            st.session_state.ma_target_source = "catalog"
        source = st.selectbox(
            "Choose from",
            ["catalog", *lists],
            format_func=lambda key: "All practices" if key == "catalog" else lists[key].name,
            key="ma_target_source",
        )
        options = list(by_id) if source == "catalog" else lists[source].practice_ids
        available = [pid for pid in options if pid in by_id]
        if len(available) != len(options):
            st.caption("Unavailable practices stay in your shortlist but cannot be assessed.")
        with st.form("ma_targets_" + source):
            revision = hashlib.sha256("|".join(required_ids).encode()).hexdigest()[:8]
            selection_key = "ma_target_choices_" + source + "_" + revision
            st.multiselect(
                "Practices",
                available,
                default=[pid for pid in required_ids if pid in available],
                format_func=lambda pid: _label(by_id[pid]),
                max_selections=3,
                key=selection_key,
            )
            st.form_submit_button(
                "Use selected practices",
                type="primary",
                on_click=_apply_target_selection,
                args=(selection_key,),
            )
        st.caption("Leave the selection empty for general acquisition or real estate questions.")


def _apply_target_selection(selection_key: str) -> None:
    # Form callbacks run before the composer is instantiated, so applying targets
    # can safely invalidate an untouched task draft even from the composer footer.
    _use_targets(st.session_state[selection_key])


def _scope_summary(context: str, callbacks: WorkspaceCallbacks) -> tuple[str, str]:
    """Read the existing snapshot contract without substituting changed buyer settings."""
    goals = context.split("Search preferences:", 1)[0].split("Applied filters:", 1)[0].strip()
    criteria = "Search criteria captured with this conversation."
    if "Applied filters: " in context:
        try:
            filters = Filters.model_validate_json(context.rsplit("Applied filters: ", 1)[1])
            criteria = callbacks.criteria_summary(filters)
        except ValueError:
            pass
    for label, heading in (
        ("Search preferences:", "Applied preferences"),
        ("Unverifiable requirements:", "Unverifiable requirements"),
    ):
        line = next((line for line in context.splitlines() if line.startswith(label)), "")
        value = line.removeprefix(label).strip()
        if value:
            criteria += f"\n\n{heading}: {value}"
    return goals or "No buyer priorities supplied.", criteria


def _active_candidates(
    question: str, history: list, selected: list[str], callbacks: WorkspaceCallbacks
) -> list[str]:
    if callbacks.resolve_candidates is not None:
        return callbacks.resolve_candidates(question, history, selected)
    # Share the backend's deterministic reference policy; this makes no model call.
    from sera.ai import investigation_ids

    return investigation_ids(question, history, selected)


def render_assistant(
    by_id: dict[str, Practice], callbacks: WorkspaceCallbacks, *, saved: SavedStore | None = None
) -> None:
    """A conversation-first workspace for acquisitions and commercial real estate."""
    context = st.session_state.get("chat_context", callbacks.effective_goals())
    required_ids = list(st.session_state.get("chat_required_ids", []))
    priorities, criteria = _scope_summary(context, callbacks)
    practices = [by_id[pid] for pid in required_ids if pid in by_id]
    ongoing = bool(st.session_state.chat or st.session_state.history)
    missing = [pid for pid in required_ids if pid not in by_id]
    if missing:
        st.warning(
            "A practice in this conversation is no longer available. Start a new conversation to choose current evidence."
        )
    if st.session_state.get("chat_context") and context != callbacks.effective_goals():
        st.info(
            "This conversation keeps the buyer goals and filters from when it began. Start a new conversation to use your current settings."
        )
    if notice := st.session_state.pop("assistant_target_notice", None):
        st.info(notice)
    if ongoing:
        st.button("Start a new conversation", on_click=_new_conversation, icon=":material/add:")
    else:
        with st.container(key="ma_tasks"):
            labels = {
                "Review a target" if practices else "Evaluate a practice",
                "Lease or buy?",
                "Assess a property",
            }
            suggestions = [task for task in deal_tasks(practices) if task.label in labels]
            for column, task in zip(st.columns(3), suggestions):
                column.button(
                    task.label,
                    help=task.description,
                    disabled=bool(missing),
                    on_click=_populate_question,
                    args=(task.request,),
                    key="starter_" + task.label,
                    width="stretch",
                )
        st.caption("Choose a starting question, or write your own below.")
    for entry in st.session_state.chat:
        with st.chat_message(entry["role"]):
            st.markdown(callbacks.buyer_answer_markdown(entry["content"]))
    if st.session_state.pop("assistant_clear_composer", False):
        st.session_state.assistant_question = ""
        st.session_state.assistant_question_draft = ""
        st.session_state.pop("assistant_task_draft", None)
    if "assistant_question" not in st.session_state:
        st.session_state.assistant_question = st.session_state.get("assistant_question_draft", "")
    with st.container(key="ma_composer"):
        question = st.text_area(
            "Ask SERA",
            key="assistant_question",
            max_chars=6000,
            height=120,
            on_change=_remember_question,
            label_visibility="collapsed",
            placeholder="What are you considering? Ask about an acquisition, a lease, or a property purchase…",
        )
        with st.container(key="ma_actions"):
            attach, send = st.columns(2, vertical_alignment="center")
            with attach:
                _target_picker(by_id, required_ids, saved, ongoing)
            with send:
                submitted = st.button(
                    "Send",
                    disabled=not callbacks.ai_configured() or bool(missing),
                    type="primary",
                    icon=":material/arrow_upward:",
                    width="stretch",
                )
        if practices:
            with st.container(key="ma_scope"):
                st.markdown("**" + " · ".join(practice.name for practice in practices) + "**")
    st.caption(
        "Fictional demo data · No live property listings · Conversation kept for this session"
    )
    if submitted and question.strip():
        try:
            active_ids = _active_candidates(
                question, st.session_state.history, required_ids, callbacks
            )
            with st.spinner("Preparing your answer…"):
                result = callbacks.investigate(
                    question, context, st.session_state.history, required_ids=required_ids
                )
            st.session_state.chat_context = context
            # Resolve from the pre-request scope, then commit only after success. The
            # backend receives the original scope so ordinal references resolve once.
            st.session_state.chat_required_ids = list(active_ids)
            st.session_state.history = result["history"]
            st.session_state.chat = (
                st.session_state.chat
                + [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": result["answer"]},
                ]
            )[-12:]
            st.session_state.last_trace = result
            st.session_state.assistant_clear_composer = True
            st.rerun()
        except DemoLimitError as error:
            st.info(str(error))
        except Exception:
            st.error(
                "The assistant could not finish. Your question and conversation are preserved. Retry with a narrower request or ask the operator to check configuration."
            )
    if submitted and not question.strip():
        st.info("Enter a question, or choose a starter prompt above.")
    if "last_trace" in st.session_state:
        callbacks.show_assessment_notice(st.session_state.last_trace)
        callbacks.show_sources(st.session_state.last_trace)
    if st.session_state.chat:
        st.download_button(
            "Export working notes",
            deal_notes(
                st.session_state.chat,
                practices,
                criteria,
                priorities,
                callbacks.buyer_answer_markdown,
                missing_targets=missing,
            ),
            file_name="sera-acquisition-notes.md",
            mime="text/markdown",
            key="export_deal_notes",
            icon=":material/download:",
        )
