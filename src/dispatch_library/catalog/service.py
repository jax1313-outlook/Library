"""`open_library()` -- a `LibraryService` backed by the catalog.

`service.LibraryService` is untouched by the persistence work; it already took
its registry and queue by injection. This module does the wiring, so the
dependency points one way: the catalog knows about the service, and the service
knows nothing about the catalog.

Both stores are given the **same connection** on purpose. Approving a candidate
writes a candidate row and an object row, and those two writes must land
together or not at all -- a catalog holding an approved candidate whose object
never arrived has lost a document and recorded that it accepted one.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from dispatch_library import ingestion
from dispatch_library.catalog.connection import open_catalog
from dispatch_library.catalog.queue import SqliteCandidateQueue
from dispatch_library.catalog.registry import SqliteObjectRegistry
from dispatch_library.models import LibraryCandidate
from dispatch_library.service import LibraryService


class CatalogLibraryService(LibraryService):
    """`LibraryService` over the catalog, plus the two things a file needs.

    Adds `review_candidate` as one transaction, and `close`. Everything else is
    inherited unchanged -- `current`, `list_current`, `resolve_packet`,
    `ingest_human_document`, `submit_candidate`, `pending_candidates`.
    """

    def __init__(self, connection: sqlite3.Connection, **kwargs) -> None:
        self.connection = connection
        super().__init__(
            registry=SqliteObjectRegistry(connection),
            candidate_queue=SqliteCandidateQueue(connection),
            **kwargs,
        )

    def review_candidate(
        self, candidate_id: str, approve: bool, reviewed_by: str
    ) -> LibraryCandidate:
        """Approve or reject, writing both rows in one transaction.

        `ingestion.review_candidate()` runs unchanged -- every refusal it makes
        is still its own: an unknown candidate, one already reviewed, a system
        identity as reviewer, or a submitter approving itself. Those raise
        before anything is written, and the transaction rolls back.

        What this adds is the guarantee the dict never needed: the candidate's
        new status and the object it produced commit together.
        """
        with self.connection:
            candidate = ingestion.review_candidate(
                self.candidate_queue, self.registry, candidate_id, approve, reviewed_by
            )
            self.candidate_queue.flush(candidate_id)
        return candidate

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CatalogLibraryService":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def open_library(path: Optional[Path | str] = None, **kwargs) -> CatalogLibraryService:
    """Open the Library at `path`, creating or migrating the catalog as needed.

    `path=None` gives an in-memory catalog: the full machinery, nothing on
    disk. Useful for a test, and honest about what it is -- it forgets, exactly
    like the dict registry it replaces.
    """
    return CatalogLibraryService(open_catalog(path), **kwargs)


@contextmanager
def library(path: Optional[Path | str] = None, **kwargs) -> Iterator[CatalogLibraryService]:
    """`with library(path) as lib:` -- closes the connection on the way out."""
    service = open_library(path, **kwargs)
    try:
        yield service
    finally:
        service.close()
