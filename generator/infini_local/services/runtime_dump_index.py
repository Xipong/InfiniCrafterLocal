"""Private, disk-backed startup facts; never reopen mutable exporter payloads."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import sqlite3
import tempfile
import threading
from typing import Any
import weakref

from infini_local.core import strict_json


def _dispose(connection: sqlite3.Connection, directory: tempfile.TemporaryDirectory) -> None:
    try:
        connection.close()
    finally:
        directory.cleanup()


class RuntimeDumpIndex:
    """Own one private database for a complete pair, with deterministic failure cleanup.

    The bounded SQLite cache spills rows and the primary-key index to disk. A
    finalized index is query-only; readers receive newly decoded row objects.
    The last mapping releases the connection and private directory, also on GC.
    """

    def __init__(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="infini-runtime-dump-")
        try:
            connection = sqlite3.connect(str(Path(directory.name) / "facts.sqlite"), check_same_thread=False)
        except BaseException:
            directory.cleanup()
            raise
        self._connection = connection
        self._lock = threading.RLock()
        self._cleanup = weakref.finalize(self, _dispose, connection, directory)
        try:
            connection.execute("PRAGMA cache_size=-2048")
            connection.execute("PRAGMA mmap_size=0")
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("CREATE TABLE facts (kind INTEGER, identity TEXT, payload BLOB, PRIMARY KEY(kind, identity)) WITHOUT ROWID")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._cleanup()

    def add(self, kind: int, identity: int, payload: bytes) -> None:
        try:
            self._connection.execute("INSERT INTO facts VALUES (?, ?, ?)", (kind, str(identity), payload))
        except sqlite3.IntegrityError as error:
            raise ValueError("snapshot_duplicate_type") from error

    def seal(self) -> None:
        self._connection.commit()
        self._connection.execute("PRAGMA query_only=ON")

    def rows(self, kind: int, count: int) -> Mapping[int, dict[str, Any]]:
        return _Rows(self, kind, count)


class _Rows(Mapping[int, dict[str, Any]]):
    def __init__(self, store: RuntimeDumpIndex, kind: int, count: int) -> None:
        self._store, self._kind, self._count = store, kind, count

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, identity: int) -> dict[str, Any]:
        if not isinstance(identity, int):
            raise KeyError(identity)
        with self._store._lock:
            row = self._store._connection.execute(
                "SELECT payload FROM facts WHERE kind=? AND identity=?", (self._kind, str(int(identity)))
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        return strict_json.loads(row[0].decode("utf-8"))

    def __iter__(self) -> Iterator[int]:
        # Keyset paging avoids keeping a cursor/lock alive across caller yields.
        last = ""
        while True:
            with self._store._lock:
                keys = self._store._connection.execute(
                    "SELECT identity FROM facts WHERE kind=? AND identity>? ORDER BY identity LIMIT 256",
                    (self._kind, last),
                ).fetchall()
            if not keys:
                return
            for (key,) in keys:
                yield int(key)
            last = keys[-1][0]

    def __eq__(self, other: object) -> bool:
        # Mapping's default comparison materializes both entire dictionaries.
        if not isinstance(other, Mapping):
            return NotImplemented
        if len(self) != len(other):
            return False
        return all(identity in other and self[identity] == other[identity] for identity in self)
