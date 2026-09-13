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
from typing import Iterator, List, Optional

from dispatch_library import ingestion
from dispatch_library.catalog import shelf as shelf_module
from dispatch_library.catalog.connection import open_catalog
from dispatch_library.catalog.queue import SqliteCandidateQueue
from dispatch_library.catalog.registry import SqliteObjectRegistry
from dispatch_library.models import LibraryCandidate, LibraryObject
from dispatch_library.service import LibraryService


class CatalogLibraryService(LibraryService):
    """`LibraryService` over the catalog, plus the two things a file needs.

    Adds `review_candidate` as one transaction, and `close`. Everything else is
    inherited unchanged -- `current`, `list_current`, `resolve_packet`,
    `ingest_human_document`, `submit_candidate`, `pending_candidates`.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        memory_root: Optional[Path | str] = None,
        **kwargs,
    ) -> None:
        self.connection = connection
        #: The shelf this catalog describes. None means the catalog is not
        #: bound to one, which is a legitimate state -- an object with an
        #: inline body needs no shelf at all.
        self.memory_root = Path(memory_root) if memory_root else None
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

    # ── the shelf ────────────────────────────────────────────────────────

    def _require_shelf(self) -> Path:
        if self.memory_root is None:
            raise ValueError(
                "this Library is not bound to a shelf; open it with "
                "open_library(path, memory_root=...) to catalogue files"
            )
        return self.memory_root

    def place_file(
        self,
        object_code: str,
        collection: str,
        title: str,
        relative_path: str,
        accepted_by: str,
        tags: Optional[List[str]] = None,
    ) -> LibraryObject:
        """Accept a file that is already on the shelf as a Library object.

        The file is read -- to hash it and measure it -- and never written,
        moved or renamed. `body_or_uri` becomes the relative path, so the
        catalog points at the document instead of holding a second copy of it
        that can fall out of date.

        `accepted_by` is the approval, exactly as in `ingest_human_document`.
        This is the only way a file on the shelf becomes a Library object: a
        scan reports what it finds and never adopts anything, because adoption
        is an acceptance and an acceptance needs a human's name on it.
        """
        root = self._require_shelf()
        path = root / relative_path
        if not path.is_file():
            raise ValueError(f"no file at {relative_path!r} under {root}")

        obj = self.ingest_human_document(
            object_code=object_code,
            collection=collection,
            title=title,
            body_or_uri=relative_path,
            accepted_by=accepted_by,
            tags=tags,
        )
        self.registry.bind_to_shelf(
            obj.object_code,
            obj.version,
            relative_path=relative_path,
            content_sha256=shelf_module.sha256_of(path),
            size_bytes=path.stat().st_size,
            observed_at=shelf_module._now(),
        )
        return obj

    def read_file(self, object_code: str) -> Optional[str]:
        """The bytes behind the CURRENT version of a shelf-backed object.

        Returns None if the object has no file. Raises if the catalog says
        there is one and there is not -- that is a MISSING finding, and
        returning None for it would make a missing document look like an
        object that never had one.
        """
        obj = self.current(object_code)
        if obj is None:
            return None
        entry = self.registry.shelf_entry(obj.object_code, obj.version)
        if entry is None:
            return None
        path = self._require_shelf() / entry["relative_path"]
        if not path.is_file():
            raise FileNotFoundError(
                f"{object_code} v{obj.version} stands for {entry['relative_path']!r}, "
                f"which is not on the shelf"
            )
        return path.read_text(encoding="utf-8")

    def scan_shelf(self, *, record: bool = True) -> "shelf_module.ScanResult":
        """Compare the shelf against the catalog. Writes nothing to the shelf."""
        return shelf_module.scan(self.connection, self._require_shelf(), record=record)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CatalogLibraryService":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def open_library(
    path: Optional[Path | str] = None,
    memory_root: Optional[Path | str] = None,
    **kwargs,
) -> CatalogLibraryService:
    """Open the Library at `path`, creating or migrating the catalog as needed.

    `path=None` gives an in-memory catalog: the full machinery, nothing on
    disk. Useful for a test, and honest about what it is -- it forgets, exactly
    like the dict registry it replaces.

    `memory_root` is the shelf -- `DISPATCH_MEMORY_ROOT`. Without it the
    Library works on inline bodies and refuses the file operations, which is
    the true answer on a machine where the shelf is not mounted.
    """
    return CatalogLibraryService(open_catalog(path), memory_root=memory_root, **kwargs)


@contextmanager
def library(
    path: Optional[Path | str] = None,
    memory_root: Optional[Path | str] = None,
    **kwargs,
) -> Iterator[CatalogLibraryService]:
    """`with library(path) as lib:` -- closes the connection on the way out."""
    service = open_library(path, memory_root=memory_root, **kwargs)
    try:
        yield service
    finally:
        service.close()
