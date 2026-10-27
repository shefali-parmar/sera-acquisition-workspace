"""Product regressions for safe lists, deterministic filters, and catalog evidence."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from sera.catalog import ROOT, budget_fit, fact_sheet, load_practices, search
from sera.models import Filters, Practice, SavedStore
from sera.storage import ListStorage, StorageConflictError, StorageError, UnknownListError


def test_list_identity_validation_never_overwrites_saved_work(tmp_path):
    storage = ListStorage(tmp_path / "lists.json")
    first = storage.create("  California targets  ")
    before = storage.path.read_bytes()
    assert storage.load().lists[0].name == "California targets"
    for name in (" ", "CALIFORNIA TARGETS"):
        with pytest.raises(ValidationError):
            storage.create(name)
        assert storage.path.read_bytes() == before
    with pytest.raises(UnknownListError, match="no longer exists"):
        storage.update("missing", delete=True)
    with pytest.raises(StorageError, match="current catalog"):
        storage.update(first, practice_ids=["not-a-practice"])
    assert storage.path.read_bytes() == before


@pytest.mark.parametrize(
    "lists",
    [
        [{"id": "same", "name": "First"}, {"id": "same", "name": "Second"}],
        [{"id": "one", "name": "First"}, {"id": "two", "name": " first "}],
        [{"id": "one", "name": "First", "practice_ids": ["SERA-001", "SERA-001"]}],
        [{"id": " ", "name": "First"}],
        [{"id": "one", "name": "First", "practice_ids": [" "]}],
    ],
)
def test_invalid_existing_store_is_reported_without_overwrite(tmp_path, lists):
    path = tmp_path / "lists.json"
    content = json.dumps({"lists": lists})
    path.write_text(content)
    storage = ListStorage(path)
    with pytest.raises(ValidationError):
        storage.create("New")
    assert path.read_text() == content
    with pytest.raises(ValidationError):
        storage.write(SavedStore())
    assert path.read_text() == content


def test_stale_snapshot_and_stale_list_edit_cannot_overwrite_new_work(tmp_path):
    storage = ListStorage(tmp_path / "lists.json")
    first = storage.create("First")
    stale = storage.load()
    storage.update(first, practice_ids=["SERA-001"])
    before = storage.path.read_bytes()
    with pytest.raises(StorageConflictError, match="another tab"):
        storage.write(stale)
    with pytest.raises(StorageConflictError):
        storage.update(first, name="Stale rename", expected_name="First", expected_practice_ids=[])
    with pytest.raises(StorageConflictError):
        storage.update(first, delete=True, expected_practice_ids=[])
    assert storage.path.read_bytes() == before


def test_threads_and_separate_processes_preserve_every_created_list(tmp_path):
    path = tmp_path / "lists.json"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: ListStorage(path).create(f"Thread {i}"), range(12)))
    code = (
        "from pathlib import Path; from sera.storage import ListStorage; import sys; "
        "storage=ListStorage(Path(sys.argv[1])); "
        "[storage.create(f'Process {sys.argv[2]} list {i}') for i in range(8)]"
    )
    processes = [
        subprocess.Popen([sys.executable, "-c", code, str(path), str(i)], cwd=ROOT)
        for i in range(3)
    ]
    assert all(process.wait(timeout=15) == 0 for process in processes)
    assert len(ListStorage(path).load().lists) == 36


@pytest.mark.parametrize("historical_id", ["RETIRED-001", "SERA-999"])
def test_unknown_historical_ids_are_retained_but_cannot_be_newly_added(tmp_path, historical_id):
    path = tmp_path / "lists.json"
    path.write_text(
        json.dumps({"lists": [{"id": "one", "name": "First", "practice_ids": [historical_id]}]})
    )
    storage = ListStorage(path)
    storage.update("one", name="Renamed")
    second = storage.create("Second")
    storage.set_memberships("SERA-001", ["one", second])
    assert storage.load().lists[0].practice_ids == [historical_id, "SERA-001"]
    before = path.read_bytes()
    with pytest.raises(StorageError):
        storage.update(second, practice_ids=[historical_id])
    assert path.read_bytes() == before


def test_failed_atomic_replace_preserves_previous_data_and_removes_temporary(tmp_path, monkeypatch):
    storage = ListStorage(tmp_path / "lists.json")
    storage.create("First")
    before = storage.path.read_bytes()

    def unavailable(*args):
        raise OSError("Read-only disk")

    monkeypatch.setattr("sera.storage.os.replace", unavailable)
    with pytest.raises(OSError, match="Read-only disk"):
        storage.create("Second")
    assert storage.path.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_default_storage_can_be_isolated_without_touching_user_lists(tmp_path, monkeypatch):
    monkeypatch.setenv("SERA_DATA_DIR", str(tmp_path / "isolated"))
    storage = ListStorage()
    storage.create("Demo")
    assert storage.path == tmp_path / "isolated" / "saved_lists.json"
    assert ListStorage(tmp_path / "explicit.json").path == tmp_path / "explicit.json"


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(state="XX"),
        lambda p: p.update(specialty="Unsupported"),
        lambda p: p.update(availability_source="SERA-002-S1"),
        lambda p: p["crime"].update(source="SERA-002-S2"),
        lambda p: p["sources"][0].update(id="SERA-002-S1"),
        lambda p: p["sources"].append(p["sources"][0]),
        lambda p: p.update(name=" "),
    ],
)
def test_catalog_rejects_broken_identity_and_source_ownership(change):
    practice = load_practices()[0].model_dump()
    change(practice)
    with pytest.raises(ValidationError):
        Practice.model_validate(practice)


def test_exact_price_boundary_and_missing_evidence_reporting():
    practice = load_practices()[0]
    inclusive = Filters(max_price=practice.asking_price)
    exclusive = Filters(max_price=practice.asking_price, max_price_inclusive=False)
    assert search([practice], inclusive) == [practice]
    assert search([practice], exclusive) == []
    assert (
        budget_fit(practice, practice.asking_price, inclusive=False) == "Above asking-price budget"
    )
    assert "sqft" in fact_sheet(practice.model_copy(update={"sqft": None}))["Missing evidence"]
    assert search([practice], Filters(keyword="  community-focused  ")) == [practice]


def test_create_list_with_initial_candidates_is_one_atomic_write(tmp_path, monkeypatch):
    storage = ListStorage(tmp_path / "lists.json")
    writes = []
    original_write = storage.write

    def capture_write(store):
        writes.append(store.model_dump())
        original_write(store)

    monkeypatch.setattr(storage, "write", capture_write)
    list_id = storage.create("First candidates", practice_ids=["SERA-001", "SERA-025", "SERA-001"])
    assert len(writes) == 1
    assert writes[0]["lists"][0]["practice_ids"] == ["SERA-001", "SERA-025"]
    saved = storage.load().lists
    assert len(saved) == 1
    assert saved[0].id == list_id
    assert saved[0].practice_ids == ["SERA-001", "SERA-025"]


def test_invalid_initial_candidate_cannot_leave_an_empty_list(tmp_path):
    storage = ListStorage(tmp_path / "lists.json")
    with pytest.raises(StorageError, match="current catalog"):
        storage.create("Invalid first candidate", practice_ids=["SERA-999"])
    assert not storage.path.exists()
    assert storage.load().lists == []
    storage.create("Existing")
    before = storage.path.read_bytes()
    with pytest.raises(StorageError, match="current catalog"):
        storage.create("Invalid new candidate", practice_ids=["SERA-001", "SERA-999"])
    assert storage.path.read_bytes() == before
    with pytest.raises(ValidationError):
        storage.create("Existing", practice_ids=["SERA-001"])
    assert storage.path.read_bytes() == before


def test_initial_candidates_and_list_are_both_preserved_on_atomic_write_failure(
    tmp_path, monkeypatch
):
    storage = ListStorage(tmp_path / "lists.json")
    storage.create("Existing", practice_ids=["SERA-025"])
    before = storage.path.read_bytes()

    def unavailable(*args):
        raise OSError("Read-only disk")

    monkeypatch.setattr("sera.storage.os.replace", unavailable)
    with pytest.raises(OSError):
        storage.create("New shortlist", practice_ids=["SERA-001"])
    assert storage.path.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []
