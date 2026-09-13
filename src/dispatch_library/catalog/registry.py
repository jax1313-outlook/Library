"""`SqliteObjectRegistry` -- the same five methods, backed by the catalog.

`ObjectRegistry` in the parent package is a dict and stays exactly as it is:
it is what the tests use and what runs with no file on disk. This class
implements the same surface against SQLite so `LibraryService` can be handed
either one and nothing else in `dispatch_library` has to know which.

    add_version · next_version · history · get_version · all_object_codes

`tests/test_registry_contract.py` runs one suite against both, which is the
only real guarantee that "the same surface" means what it says.

**One behaviour deliberately differs, and it is the honest direction.**
`ObjectRegistry.add_version` supersedes the previous version by mutating the
Python object the caller still holds, so a caller watching `v1.status` sees it
change. A row in a database cannot reach into a caller's variable. Reading
`registry.history()` or `resolver.current()` gives the same answer from both;
holding an old instance and expecting it to update gives the right answer only
from the dict. The contract suite pins the behaviour that is true of both, and
`test_the_difference_from_the_dict_registry` states the one that is not.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from dispatch_library.models import (
    LibraryObject,
    LibraryObjectSource,
    LibraryObjectStatus,
)

_COLUMNS = (
    "object_code, version, collection, title, status, source, body_or_uri, "
    "accepted_by, accepted_at, supersedes_version, relative_path, "
    "content_sha256, size_bytes, observed_at"
)


def _to_object(row: sqlite3.Row) -> LibraryObject:
    """A catalog row as a `LibraryObject`.

    The dataclass validates in `__post_init__` -- collection membership and the
    no-system-identity rule -- so a row that somehow violated either would raise
    here rather than be handed to a caller as truth. That is the intended
    behaviour: the catalog is not more authoritative than the object model.
    """
    return LibraryObject(
        object_code=row["object_code"],
        collection=row["collection"],
        title=row["title"],
        version=row["version"],
        status=LibraryObjectStatus(row["status"]),
        source=LibraryObjectSource(row["source"]),
        body_or_uri=row["body_or_uri"],
        accepted_by=row["accepted_by"],
        accepted_at=row["accepted_at"],
        supersedes_version=row["supersedes_version"],
    )


class SqliteObjectRegistry:
    """Versioned object storage in the catalog.

    Holds a connection; does not own it. The caller opens the catalog and may
    hand the same connection to the candidate queue, so that a candidate
    approval -- which writes a candidate row *and* an object row -- is one
    transaction rather than two that can half-happen.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection

    # ── the five-method surface ──────────────────────────────────────────

    def add_version(self, obj: LibraryObject) -> LibraryObject:
        """Record a version, superseding the previous CURRENT one atomically.

        S3. The flip and the insert are one transaction, because between them
        the catalog holds a state the resolver is not allowed to see: either no
        CURRENT version of this code, or -- if they ran in the other order --
        two. A crash in that window used to be impossible only because the
        store was a dict and the process died with it. On disk the window is
        real, so it is closed here rather than documented.

        The unique partial index is the second line of defence: if this method
        is ever rewritten to do the two writes apart, the database refuses the
        second CURRENT rather than accepting a state `current()` cannot read.
        """
        with self._db:  # BEGIN ... COMMIT, or ROLLBACK on any exception
            if obj.status == LibraryObjectStatus.CURRENT:
                self._db.execute(
                    "UPDATE library_object SET status = 'SUPERSEDED' "
                    "WHERE object_code = ? AND status = 'CURRENT'",
                    (obj.object_code,),
                )
            self._db.execute(
                f"INSERT INTO library_object ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    obj.object_code, obj.version, obj.collection, obj.title,
                    obj.status.value, obj.source.value, obj.body_or_uri,
                    obj.accepted_by, obj.accepted_at, obj.supersedes_version,
                    None, None, None, None,
                ),
            )
            for position, tag in enumerate(obj.tags):
                self._db.execute(
                    "INSERT OR IGNORE INTO library_object_tag "
                    "(object_code, version, tag, position) VALUES (?, ?, ?, ?)",
                    (obj.object_code, obj.version, tag, position),
                )
        return obj

    def next_version(self, object_code: str) -> int:
        row = self._db.execute(
            "SELECT max(version) AS v FROM library_object WHERE object_code = ?",
            (object_code,),
        ).fetchone()
        return 1 if row["v"] is None else int(row["v"]) + 1

    def history(self, object_code: str) -> List[LibraryObject]:
        """Every version of one code, oldest first -- the dict's ordering."""
        rows = self._db.execute(
            f"SELECT {_COLUMNS} FROM library_object WHERE object_code = ? ORDER BY version",
            (object_code,),
        ).fetchall()
        return [self._with_tags(_to_object(row)) for row in rows]

    def get_version(self, object_code: str, version: int) -> Optional[LibraryObject]:
        row = self._db.execute(
            f"SELECT {_COLUMNS} FROM library_object WHERE object_code = ? AND version = ?",
            (object_code, version),
        ).fetchone()
        return self._with_tags(_to_object(row)) if row else None

    def all_object_codes(self) -> List[str]:
        return [
            row["object_code"]
            for row in self._db.execute(
                "SELECT DISTINCT object_code FROM library_object ORDER BY object_code"
            )
        ]

    # ── the shelf ────────────────────────────────────────────────────────

    def bind_to_shelf(
        self,
        object_code: str,
        version: int,
        *,
        relative_path: str,
        content_sha256: str,
        size_bytes: int,
        observed_at: str,
    ) -> None:
        """Record which file on the shelf a version stands for.

        Separate from `add_version` on purpose. Placing a document and
        cataloguing where its bytes live are two different acts, and an object
        with an inline body has no file at all.
        """
        with self._db:
            self._db.execute(
                "UPDATE library_object SET relative_path = ?, content_sha256 = ?, "
                "size_bytes = ?, observed_at = ? WHERE object_code = ? AND version = ?",
                (relative_path, content_sha256, size_bytes, observed_at, object_code, version),
            )

    def shelf_entry(self, object_code: str, version: int) -> Optional[dict]:
        row = self._db.execute(
            "SELECT relative_path, content_sha256, size_bytes, observed_at "
            "FROM library_object WHERE object_code = ? AND version = ?",
            (object_code, version),
        ).fetchone()
        if row is None or row["relative_path"] is None:
            return None
        return dict(row)

    def current_shelf_entries(self) -> List[dict]:
        """Every CURRENT object that stands for a file, for the scan to check."""
        return [
            dict(row)
            for row in self._db.execute(
                "SELECT object_code, version, relative_path, content_sha256, size_bytes "
                "FROM library_object "
                "WHERE status = 'CURRENT' AND relative_path IS NOT NULL "
                "ORDER BY relative_path"
            )
        ]

    # ── internals ────────────────────────────────────────────────────────

    def _with_tags(self, obj: LibraryObject) -> LibraryObject:
        obj.tags = [
            row["tag"]
            for row in self._db.execute(
                "SELECT tag FROM library_object_tag "
                "WHERE object_code = ? AND version = ? ORDER BY position",
                (obj.object_code, obj.version),
            )
        ]
        return obj
