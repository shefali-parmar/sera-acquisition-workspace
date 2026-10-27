"""Validated single-user JSON with atomic writes and serialized local mutations."""

import hashlib
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sera.catalog import ROOT, load_practices
from sera.models import SavedList, SavedStore

_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class StorageError(ValueError):
    """An actionable saved-list operation failure."""


class StorageConflictError(StorageError):
    """The saved content changed after the caller loaded it."""


class UnknownListError(StorageError):
    """The selected list no longer exists."""


def _revision(content: bytes | None) -> str:
    return "missing" if content is None else hashlib.sha256(content).hexdigest()


class ListStorage:
    def __init__(self, path: Path | None = None, *, valid_practice_ids=None):
        default_dir = Path(os.environ.get("SERA_DATA_DIR", ROOT / "local_data"))
        self.path = Path(path) if path is not None else default_dir / "saved_lists.json"
        self.path = self.path.expanduser().resolve()
        self.valid_practice_ids = (
            {practice.id for practice in load_practices()}
            if valid_practice_ids is None
            else set(valid_practice_ids)
        )
        with _LOCKS_GUARD:
            self._thread_lock = _LOCKS.setdefault(self.path, threading.RLock())
        self._local = threading.local()

    @contextmanager
    def _locked(self):
        """Keep read-modify-write indivisible across threads and local app processes."""
        with self._thread_lock:
            if getattr(self._local, "held", False):
                yield
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # A stable sidecar is needed: atomic replacement changes the data file's inode.
            with self.path.with_suffix(self.path.suffix + ".lock").open("a+b") as lock:
                if os.name == "nt":
                    import msvcrt

                    lock.seek(0, os.SEEK_END)
                    if lock.tell() == 0:
                        lock.write(b"0")
                        lock.flush()
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            lock.seek(0)
                            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise StorageError("Saved lists are busy. Please retry.") from None
                            time.sleep(0.05)
                else:
                    import fcntl

                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() >= deadline:
                                raise StorageError("Saved lists are busy. Please retry.") from None
                            time.sleep(0.05)
                self._local.held = True
                try:
                    yield
                finally:
                    self._local.held = False
                    if os.name == "nt":
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _content(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def load(self) -> SavedStore:
        # Invalid content raises and remains untouched; unknown historical IDs are retained.
        content = self._content()
        store = SavedStore.model_validate_json(content) if content is not None else SavedStore()
        store._storage_revision = _revision(content)
        return store

    def write(self, store: SavedStore) -> None:
        """Write a loaded snapshot only if the file has not changed since that load."""
        with self._locked():
            validated = SavedStore.model_validate(store.model_dump())
            current = self.load()  # Never overwrite a corrupt existing file.
            if store._storage_revision != current._storage_revision:
                raise StorageConflictError("Saved lists changed in another tab. Reload and retry.")
            previous_members = {item.id: set(item.practice_ids) for item in current.lists}
            for item in validated.lists:
                added = set(item.practice_ids) - previous_members.get(item.id, set())
                self._validate_practices(added)
            handle, temporary = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            try:
                payload = validated.model_dump_json(indent=2).encode("utf-8")
                with os.fdopen(handle, "wb") as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
                store._storage_revision = _revision(payload)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def _validate_practices(self, practice_ids) -> None:
        if set(practice_ids) - self.valid_practice_ids:
            raise StorageError(
                "A selected practice is not in the current catalog. Reload and retry."
            )

    def create(self, name: str, *, practice_ids: list[str] | None = None) -> str:
        """Create a list with its initial candidates in one validated transaction."""
        with self._locked():
            store = self.load()
            item = SavedList(
                id=str(uuid4()), name=name, practice_ids=list(dict.fromkeys(practice_ids or []))
            )
            store.lists.append(item)
            self.write(store)
            return item.id

    def update(
        self,
        list_id: str,
        *,
        name: str | None = None,
        practice_ids: list[str] | None = None,
        delete: bool = False,
        expected_name: str | None = None,
        expected_practice_ids: list[str] | None = None,
    ) -> None:
        with self._locked():
            store = self.load()
            item = next((item for item in store.lists if item.id == list_id), None)
            if item is None:
                raise UnknownListError(
                    "This saved list no longer exists. Reload and choose a list."
                )
            if (expected_name is not None and expected_name != item.name) or (
                expected_practice_ids is not None and expected_practice_ids != item.practice_ids
            ):
                raise StorageConflictError("This list changed in another tab. Reload and retry.")
            if delete:
                store.lists.remove(item)
            else:
                if name is not None:
                    item.name = name.strip()
                if practice_ids is not None:
                    item.practice_ids = list(dict.fromkeys(practice_ids))
            self.write(store)

    def set_memberships(self, practice_id: str, list_ids: list[str]) -> None:
        """Save or unsave one practice without overwriting other practices' memberships."""
        with self._locked():
            store = self.load()
            self._validate_practices([practice_id])
            selected = set(list_ids)
            if selected - {item.id for item in store.lists}:
                raise UnknownListError("A selected list no longer exists. Reload and retry.")
            for item in store.lists:
                item.practice_ids = [pid for pid in item.practice_ids if pid != practice_id]
                if item.id in selected:
                    item.practice_ids.append(practice_id)
            self.write(store)
