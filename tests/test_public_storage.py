"""Public visitors must never share shortlist data or write it to disk."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from sera.catalog import load_practices
from sera.exports import build_list_export, export_csv, export_json
from sera.models import Filters, SavedList
from sera.storage import SessionListStorage, StorageConflictError, StorageError, UnknownListError

IDS = {"SERA-001", "SERA-002"}


def storage(state=None):
    return SessionListStorage({} if state is None else state, valid_practice_ids=IDS)


def test_visitors_cannot_see_or_change_other_sessions():
    first, second = storage(), storage()
    first_id = first.create("Private first", practice_ids=["SERA-001"])
    assert second.load().lists == []
    with pytest.raises(UnknownListError):
        second.update(first_id, name="Stolen")
    with pytest.raises(UnknownListError):
        second.set_memberships("SERA-001", [first_id])
    second.create("Private second", practice_ids=["SERA-002"])
    assert [item.name for item in first.load().lists] == ["Private first"]


def test_snapshots_are_independent_and_survive_backend_recreation():
    state = {}
    backend = storage(state)
    backend.create("Original", practice_ids=["SERA-001"])
    snapshot = backend.load()
    snapshot.lists[0].name = "Unwritten"
    snapshot.lists[0].practice_ids.append("SERA-002")
    current = storage(state).load()
    assert current.lists[0].name == "Original"
    assert current.lists[0].practice_ids == ["SERA-001"]
    backend.write(snapshot)
    snapshot.lists.clear()
    assert storage(state).load().lists[0].name == "Unwritten"


def test_concurrent_transactions_on_same_session_do_not_lose_lists():
    state = {}

    def create(index):
        return storage(state).create(f"List {index}", practice_ids=["SERA-001"])

    with ThreadPoolExecutor(max_workers=4) as workers:
        created = list(workers.map(create, range(12)))
    assert {item.id for item in storage(state).load().lists} == set(created)


def test_rename_multiple_memberships_delete_and_export():
    backend = storage()
    first_id = backend.create("First", practice_ids=["SERA-001"])
    second_id = backend.create("Second", practice_ids=["SERA-002"])
    backend.update(first_id, name="Renamed", expected_name="First")
    backend.set_memberships("SERA-001", [first_id, second_id])
    first, second = backend.load().lists
    assert first.name == "Renamed"
    assert second.practice_ids == ["SERA-002", "SERA-001"]
    by_id = {practice.id: practice for practice in load_practices()}
    payload = build_list_export(second, by_id, filters=Filters(), buyer_goals="Transition")
    assert json.loads(export_json(payload))["list"]["practice_ids"] == second.practice_ids
    assert "SERA-001" in export_csv(payload)
    backend.update(first_id, delete=True)
    assert [item.id for item in backend.load().lists] == [second_id]


def test_stale_snapshots_and_edit_expectations_are_rejected():
    backend = storage()
    list_id = backend.create("First", practice_ids=["SERA-001"])
    stale = backend.load()
    backend.update(list_id, name="Updated")
    with pytest.raises(StorageConflictError):
        backend.write(stale)
    with pytest.raises(StorageConflictError):
        backend.update(list_id, name="Overwrite", expected_name="First")
    with pytest.raises(StorageConflictError):
        backend.update(list_id, practice_ids=[], expected_practice_ids=[])
    assert backend.load().lists[0].name == "Updated"


def test_invalid_first_list_and_memberships_leave_no_partial_state():
    state = {}
    backend = storage(state)
    with pytest.raises(StorageError):
        backend.create("Invalid", practice_ids=["NOT-IN-CATALOG"])
    assert state == {}
    with pytest.raises(ValidationError):
        backend.create("   ", practice_ids=["SERA-001"])
    list_id = backend.create("Valid", practice_ids=["SERA-001"])
    before = dict(state)
    with pytest.raises(StorageError):
        backend.update(list_id, practice_ids=["UNKNOWN"])
    with pytest.raises(StorageError):
        backend.set_memberships("UNKNOWN", [list_id])
    with pytest.raises(ValidationError):
        backend.create("VALID")
    assert state == before


def test_snapshot_schema_validation_and_corruption_are_preserved():
    state = {}
    backend = storage(state)
    backend.create("First")
    snapshot = backend.load()
    snapshot.lists.append(SavedList(id=snapshot.lists[0].id, name="Duplicate ID"))
    with pytest.raises(ValidationError):
        backend.write(snapshot)
    assert len(backend.load().lists) == 1
    state[backend._state_key] = b"not JSON"
    with pytest.raises(ValidationError):
        backend.create("Cannot overwrite")
    assert state[backend._state_key] == b"not JSON"


def test_session_transactions_do_not_access_files_or_accept_paths(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Session storage must not access the filesystem")

    for method in ("open", "read_bytes", "write_bytes", "mkdir"):
        monkeypatch.setattr(Path, method, fail)
    backend = storage()
    list_id = backend.create("No disk", practice_ids=["SERA-001"])
    backend.update(list_id, name="Still no disk")
    backend.set_memberships("SERA-002", [list_id])
    assert backend.load().lists[0].practice_ids == ["SERA-001", "SERA-002"]
    backend.update(list_id, delete=True)
    assert backend.load().lists == []
    with pytest.raises(TypeError):
        SessionListStorage({}, path="visitor-controlled.json")
