"""M&A task scoping and visible-notes export contracts."""

from sera.ai import investigation_ids
from sera.catalog import load_practices
from sera.ma_workspace import deal_notes, deal_tasks


def test_each_targeted_task_resolves_the_selected_records_before_discovery():
    records = load_practices()
    chosen = [records[0], records[24]]
    for task in deal_tasks(chosen):
        assert investigation_ids(task.request, [], ["SERA-007"]) == ["SERA-001", "SERA-025"]
        assert all(practice.name in task.request for practice in chosen)


def test_notes_use_visible_exchanges_and_captured_context():
    result = deal_notes(
        [
            {"role": "user", "content": "What should I verify?"},
            {"role": "assistant", "content": "Revenue is reported; profit is unknown."},
        ],
        [load_practices()[0]],
        "Under $1,000,000",
        "Seller transition",
        lambda value: value,
    )
    assert "Riverbend Dermatology" in result
    assert "Under $1,000,000" in result and "Seller transition" in result
    assert "## Buyer\n\nWhat should I verify?" in result
    assert "profit is unknown" in result
    assert "completed due diligence" in result


def test_notes_preserve_unavailable_target_scope_instead_of_claiming_catalog_research():
    result = deal_notes(
        [{"role": "assistant", "content": "Earlier assessment"}],
        [],
        "Any location",
        "Transition",
        lambda value: value,
        missing_targets=["SERA-999"],
    )
    assert "Unavailable practice (SERA-999)" in result
    assert "Current targets:** Catalog research" not in result
