"""`CatalogLibraryService` -- `LibraryService` with a memory, and `open_library()`.

Every method `LibraryService` had keeps its name, arguments and return type, so Publisher, Joe
and Intelligence hold the same boundary they held before. What changes is that the answers
survive the process, and that the stricter v2 rules apply:

  * `ingest_human_document` still accepts directly, with no second gate, but needs an
    `object_type`. Without one it refuses and a MISSING_FIELD notice records the asset.
  * `review_candidate` approves only a VALIDATED candidate. `validate_candidate` is Library's
    step; `confirm_object_type` is the submitting source's or a human's.
  * `resolve_packet` and `current_for_external_use` never hand out a REVIEW_DUE asset.
  * `get_recipe` exists. Publisher's `LibraryClient` protocol has always called it.

The service never approves anything itself and never writes to the shelf.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

from dispatch_library.catalog.connection import open_catalog
from dispatch_library.catalog.queue import SqliteCandidateQueue, candidate_from_row, submit_from_contract
from dispatch_library.catalog.registry import SqliteObjectRegistry, object_from_row
from dispatch_library.catalog.store import Catalog, CatalogRefusal, NotFound, ScanReport
from dispatch_library.models import LibraryCandidate, LibraryObject, PublisherRecipe, RecipeType
from dispatch_library.recipes import MISSING
from dispatch_library.service import LibraryService

CATALOG_ENV = "DISPATCH_LIBRARY_CATALOG"
MEMORY_ENV = "DISPATCH_MEMORY_ROOT"

PathLike = Union[str, Path]


def _type_value(recipe_type) -> str:
    return getattr(recipe_type, "value", recipe_type)


class CatalogLibraryService(LibraryService):
    def __init__(self, catalog: Catalog, *, consumer_role: str = "LIBRARY_SERVICE") -> None:
        self.catalog = catalog
        self.connection = catalog.db
        self.memory_root = catalog.memory_root
        self.consumer_role = consumer_role
        super().__init__(
            registry=SqliteObjectRegistry(catalog),
            candidate_queue=SqliteCandidateQueue(catalog),
        )

    # ── reads ────────────────────────────────────────────────────────────

    def _object(self, row) -> LibraryObject:
        obj = object_from_row(row, self.catalog.tags(row["object_code"]))
        return obj

    def current(self, object_code: str) -> Optional[LibraryObject]:
        """The current version, REVIEW_DUE included, with its lifecycle state on it."""
        row, _ = self.catalog.retrieve(object_code, consumer_role=self.consumer_role, for_external_use=False)
        return self._object(row) if row is not None else None

    def current_for_external_use(self, object_code: str, *, purpose: str = "") -> Optional[LibraryObject]:
        """The current version only if it may leave the building: REVIEW_DUE comes back None."""
        row, _ = self.catalog.retrieve(object_code, consumer_role=self.consumer_role, purpose=purpose,
                                       for_external_use=True)
        return self._object(row) if row is not None else None

    def availability(self, object_code: str, *, purpose: str = "") -> Dict[str, object]:
        row, outcome = self.catalog.retrieve(object_code, consumer_role=self.consumer_role, purpose=purpose,
                                             for_external_use=True)
        return {"outcome": outcome, "object": self._object(row) if row is not None else None}

    def list_current(self, collection: Optional[str] = None) -> List[LibraryObject]:
        return [self._object(row) for row in self.catalog.list_current(collection)]

    def history(self, object_code: str) -> List[LibraryObject]:
        return self.registry.history(object_code)

    # ── recipes ──────────────────────────────────────────────────────────

    def get_recipe(self, recipe_type) -> Optional[Dict[str, object]]:
        return self.catalog.recipe(_type_value(recipe_type))

    def load_recipes(self, path: PathLike) -> Dict[str, List[str]]:
        return self.catalog.load_recipes(Path(path))

    def register_recipe(self, recipe: PublisherRecipe) -> PublisherRecipe:
        raise CatalogRefusal(
            "recipes enter the catalog from publisher_recipes.json through load_recipes(), so their "
            "source and hash are recorded; an in-process PublisherRecipe has neither"
        )

    def resolve_packet(self, recipe_type) -> Dict[str, object]:
        """{object_code: LibraryObject | "MISSING"} for the recipe's company items.

        A REVIEW_DUE object resolves to MISSING: Publisher's `pull_libraries` treats anything that
        is not MISSING as usable, so a blocked credential must not arrive as an object.
        `resolve_packet_detail` says which MISSING is which.
        """
        return {code: (detail["object"] if detail["outcome"] == "RETURNED" else MISSING)
                for code, detail in self.resolve_packet_detail(recipe_type).items()}

    def resolve_packet_detail(self, recipe_type) -> Dict[str, Dict[str, object]]:
        recipe = self.get_recipe(recipe_type)
        if recipe is None:
            return {}
        result = {}
        for code in recipe["required_library_object_codes"]:
            result[code] = self.availability(code, purpose=f"resolve_packet {_type_value(recipe_type)}")
        return result

    # ── placement ────────────────────────────────────────────────────────

    def ingest_human_document(
        self,
        object_code: str,
        collection: str,
        title: str,
        body_or_uri: str,
        accepted_by: str,
        tags: Optional[List[str]] = None,
        *,
        object_type: Optional[str] = None,
        capture_channel: Optional[str] = None,
        capture_ref: Optional[str] = None,
        minor: bool = False,
        review_due_date: Optional[str] = None,
    ) -> LibraryObject:
        row = self.catalog.place(
            object_code=object_code, collection=collection, title=title, accepted_by=accepted_by,
            object_type=object_type, body=body_or_uri, tags=tags or (), minor=minor,
            capture_channel=capture_channel, capture_ref=capture_ref, review_due_date=review_due_date,
        )
        return self.registry._with_prior_link(self._object(row))

    def place_file(
        self,
        object_code: str,
        collection: str,
        title: str,
        relative_path: str,
        accepted_by: str,
        tags: Optional[List[str]] = None,
        *,
        object_type: Optional[str] = None,
        capture_channel: Optional[str] = None,
        minor: bool = False,
    ) -> LibraryObject:
        """Accept a file already on the shelf. Read to hash; never written, moved or renamed."""
        row = self.catalog.place(
            object_code=object_code, collection=collection, title=title, accepted_by=accepted_by,
            object_type=object_type, relative_path=relative_path, tags=tags or (), minor=minor,
            capture_channel=capture_channel,
        )
        return self.registry._with_prior_link(self._object(row))

    def set_lifecycle(self, object_code: str, state: str) -> LibraryObject:
        return self._object(self.catalog.set_lifecycle(object_code, state))

    # ── candidates ───────────────────────────────────────────────────────

    def submit_candidate(self, candidate) -> LibraryCandidate:
        return submit_from_contract(self.catalog, candidate)

    def candidate(self, candidate_id: str) -> Optional[LibraryCandidate]:
        return self.candidate_queue.get(candidate_id)

    def classify_candidate(self, candidate_id: str, recommended_object_type: str) -> LibraryCandidate:
        return candidate_from_row(self.catalog.classify_candidate(candidate_id, recommended_object_type))

    def confirm_object_type(self, candidate_id: str, object_type: str, confirmed_by: str) -> LibraryCandidate:
        return candidate_from_row(self.catalog.confirm_object_type(candidate_id, object_type, confirmed_by))

    def validate_candidate(self, candidate_id: str) -> Dict[str, object]:
        passed, problems = self.catalog.validate_candidate(candidate_id)
        return {"passed": passed, "problems": problems, "candidate": self.candidate(candidate_id)}

    def review_candidate(self, candidate_id: str, approve: bool, reviewed_by: str, *,
                         capture_channel: Optional[str] = None, capture_ref: Optional[str] = None) -> LibraryCandidate:
        if self.catalog.candidate_row(candidate_id) is None:
            raise ValueError(f"no candidate {candidate_id!r} in queue")
        row = self.catalog.decide_candidate(candidate_id, "APPROVED" if approve else "REJECTED", reviewed_by,
                                            capture_channel=capture_channel, capture_ref=capture_ref)
        return candidate_from_row(row)

    def defer_candidate(self, candidate_id: str, reviewed_by: str, notes: str = "") -> LibraryCandidate:
        return candidate_from_row(self.catalog.decide_candidate(candidate_id, "DEFERRED", reviewed_by, notes=notes))

    def pending_candidates(self) -> List[LibraryCandidate]:
        return self.candidate_queue.pending()

    # ── notices, shelf, lifecycle ────────────────────────────────────────

    def notices(self, status: Optional[str] = "OPEN") -> List[dict]:
        return [dict(row) for row in self.catalog.notices(status)]

    def resolve_notice(self, notice_id: str, resolved_by: str, resolution: str) -> dict:
        return dict(self.catalog.resolve_notice(notice_id, resolved_by, resolution))

    def scan_shelf(self, *, record: bool = True) -> ScanReport:
        if self.memory_root is None:
            raise CatalogRefusal("this Library is not bound to a shelf; open it with memory_root")
        return self.catalog.scan(self.memory_root, record=record)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CatalogLibraryService":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def open_library(
    path: Optional[PathLike] = None,
    memory_root: Optional[PathLike] = None,
    *,
    consumer_role: str = "LIBRARY_SERVICE",
) -> CatalogLibraryService:
    """Open the Library at `path`, creating schema version 2 in a new file.

    `path=None` gives an in-memory catalog with every rule and nothing on disk. `memory_root`
    is the shelf; without it the Library works on inline bodies and refuses file operations.
    """
    catalog = Catalog(open_catalog(path), memory_root=Path(memory_root) if memory_root else None)
    return CatalogLibraryService(catalog, consumer_role=consumer_role)


def open_configured_library(*, consumer_role: str = "LIBRARY_SERVICE") -> Optional[CatalogLibraryService]:
    """The Library named by DISPATCH_LIBRARY_CATALOG, bound to DISPATCH_MEMORY_ROOT; None if unset."""
    path = os.environ.get(CATALOG_ENV, "").strip()
    if not path:
        return None
    memory = os.environ.get(MEMORY_ENV, "").strip() or None
    return open_library(path, memory_root=memory, consumer_role=consumer_role)


@contextmanager
def library(path: Optional[PathLike] = None, memory_root: Optional[PathLike] = None,
            **kwargs) -> Iterator[CatalogLibraryService]:
    service = open_library(path, memory_root=memory_root, **kwargs)
    try:
        yield service
    finally:
        service.close()
