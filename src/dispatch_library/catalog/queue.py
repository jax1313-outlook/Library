"""`SqliteCandidateQueue` -- the Library Candidate Queue, on disk.

Same four methods as `ingestion.CandidateQueue`: `add`, `get`, `pending`,
`all`. `ingestion.review_candidate()` drives it unchanged.

Durability is the whole point. A candidate is a nomination waiting for a human
to look at it, and a queue that empties when the process exits cannot hold one:
the wait is measured in days, and the process is not. Until now an Intelligence
finding routed to Library survived until the program closed, which is another
way of saying it did not survive.

One subtlety worth knowing about. `review_candidate()` mutates the candidate
object it fetched and then, if approved, writes an object into the registry --
two writes that must not half-happen. `get()` returns a live handle rather than
a detached copy, and `flush()` persists it; `ingestion` never calls `flush`,
so `review_candidate` is wrapped here by `reviewing()` in service.py, which
holds one transaction across both stores. Where the queue and the registry
share a connection -- which is how `open_library()` wires them -- that
transaction covers both.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from dispatch_library.models import (
    LibraryCandidate,
    LibraryCandidateStatus,
    SubmittedBy,
)

_COLUMNS = (
    "candidate_id, submitted_by, source_type, collection, proposed_object_code, "
    "proposed_title, proposed_body_or_reference, source_finding_id, status, "
    "reviewed_by, reviewed_at, created_at"
)


def _to_candidate(row: sqlite3.Row) -> LibraryCandidate:
    return LibraryCandidate(
        submitted_by=SubmittedBy(row["submitted_by"]),
        source_type=row["source_type"],
        collection=row["collection"],
        proposed_object_code=row["proposed_object_code"],
        proposed_title=row["proposed_title"],
        proposed_body_or_reference=row["proposed_body_or_reference"],
        source_finding_id=row["source_finding_id"],
        status=LibraryCandidateStatus(row["status"]),
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        candidate_id=row["candidate_id"],
        created_at=row["created_at"],
    )


class SqliteCandidateQueue:
    """Nominations awaiting human review, held in the catalog.

    Holds a connection; does not own it. Sharing one with
    `SqliteObjectRegistry` is what lets an approval -- a candidate row and an
    object row -- commit or roll back together.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._db = connection
        #: Candidates handed out by `get()`, so `flush()` can write back the
        #: mutations `ingestion.review_candidate()` makes in place. Keyed by id
        #: so two `get()` calls for one candidate return the same object and a
        #: caller cannot end up reviewing a stale copy.
        self._live: Dict[str, LibraryCandidate] = {}

    def add(self, candidate: LibraryCandidate) -> LibraryCandidate:
        with self._db:
            self._db.execute(
                f"INSERT INTO library_candidate ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate.candidate_id, candidate.submitted_by.value,
                    candidate.source_type, candidate.collection,
                    candidate.proposed_object_code, candidate.proposed_title,
                    candidate.proposed_body_or_reference, candidate.source_finding_id,
                    candidate.status.value, candidate.reviewed_by,
                    candidate.reviewed_at, candidate.created_at,
                ),
            )
        self._live[candidate.candidate_id] = candidate
        return candidate

    def get(self, candidate_id: str) -> Optional[LibraryCandidate]:
        """The candidate, as a handle whose changes `flush()` will persist.

        Returns the same object for repeated calls. Two different objects for
        one candidate would let a caller review one and persist the other.
        """
        if candidate_id in self._live:
            return self._live[candidate_id]
        row = self._db.execute(
            f"SELECT {_COLUMNS} FROM library_candidate WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            return None
        candidate = _to_candidate(row)
        self._live[candidate_id] = candidate
        return candidate

    def pending(self) -> List[LibraryCandidate]:
        """Everything still waiting on a person, oldest first.

        Oldest first because this is a work queue: the nomination that has been
        waiting longest is the one most likely to be forgotten.
        """
        return [
            self._track(_to_candidate(row))
            for row in self._db.execute(
                f"SELECT {_COLUMNS} FROM library_candidate "
                "WHERE status = 'PENDING_REVIEW' ORDER BY created_at, candidate_id"
            )
        ]

    def all(self) -> List[LibraryCandidate]:
        return [
            self._track(_to_candidate(row))
            for row in self._db.execute(
                f"SELECT {_COLUMNS} FROM library_candidate ORDER BY created_at, candidate_id"
            )
        ]

    def flush(self, candidate_id: str) -> None:
        """Write a handed-out candidate's current state back to the catalog.

        `ingestion.review_candidate()` mutates the candidate in place, which is
        the right design for a dict and invisible to a database. This is the
        one line that makes the difference, and `service.reviewing()` is what
        guarantees it runs inside the same transaction as the object write.
        """
        candidate = self._live.get(candidate_id)
        if candidate is None:
            return
        self._db.execute(
            "UPDATE library_candidate SET status = ?, reviewed_by = ?, reviewed_at = ? "
            "WHERE candidate_id = ?",
            (
                candidate.status.value, candidate.reviewed_by,
                candidate.reviewed_at, candidate_id,
            ),
        )

    def _track(self, candidate: LibraryCandidate) -> LibraryCandidate:
        existing = self._live.get(candidate.candidate_id)
        if existing is not None:
            return existing
        self._live[candidate.candidate_id] = candidate
        return candidate
