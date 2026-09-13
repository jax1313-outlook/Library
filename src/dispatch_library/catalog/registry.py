"""`SqliteObjectRegistry` -- the five-method registry surface over catalog schema version 2.

    add_version · next_version · history · get_version · all_object_codes

`tests/test_registry_contract.py` runs one suite against this and the in-memory
`ObjectRegistry`, which is the only real guarantee that the two answer alike.

Where version 2 is stricter than the dict, it refuses rather than pretends:

  * `add_version` with `DRAFT_CANDIDATE` -- a draft is a candidate row, not a version.
  * `add_version` with `APPROVED_CANDIDATE` -- approving a candidate is `review_candidate`, which
    writes the candidate decision and the version together.
  * `add_version` with no `object_type`, for an object the catalog has never seen (ruling 3).

The integer `version` of the shared contract is the MAJOR part; `version_minor` carries the rest.
`get_version(code, n)` means `n.0`.
"""
from __future__ import annotations

from typing import List, Optional

from dispatch_library.catalog.store import Catalog, CatalogRefusal
from dispatch_library.models import (
    LibraryObject,
    LibraryObjectSource,
    LibraryObjectStatus,
)


def object_from_row(row, tags: Optional[List[str]] = None) -> LibraryObject:
    """A catalog version row as the shared-contract `LibraryObject`."""
    state = row["lifecycle_state"]
    is_current = state in ("CURRENT", "ACTIVE_USE", "REVIEW_DUE")
    source = (LibraryObjectSource.APPROVED_CANDIDATE if row["approval_basis"] == "CANDIDATE_REVIEW"
              else LibraryObjectSource.HUMAN_PLACED)
    body = row["body"] if row["body"] is not None else row["content_uri"]
    if row["relative_path"]:
        body = row["relative_path"]
    return LibraryObject(
        object_code=row["object_code"],
        collection=row["collection_id"],
        title=row["title"],
        version=row["version_major"],
        status=LibraryObjectStatus.CURRENT if is_current else LibraryObjectStatus.SUPERSEDED,
        source=source,
        body_or_uri=body,
        accepted_by=row["approver"],
        accepted_at=row["approved_at"],
        supersedes_version=None,
        tags=list(tags or []),
        version_minor=row["version_minor"],
        object_type=row["object_type"],
        lifecycle_state=state,
        capture_channel=row["capture_channel"],
        library_object_id=row["library_object_id"],
    )


class SqliteObjectRegistry:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def add_version(self, obj: LibraryObject) -> LibraryObject:
        if obj.status == LibraryObjectStatus.DRAFT_CANDIDATE:
            raise CatalogRefusal(
                "a draft is a Library candidate, not a version; submit it with submit_candidate()"
            )
        if obj.status != LibraryObjectStatus.CURRENT:
            raise CatalogRefusal("a version enters the catalog as CURRENT; older versions are made by superseding")
        if obj.source == LibraryObjectSource.APPROVED_CANDIDATE:
            raise CatalogRefusal("an approved candidate is written by review_candidate(), with its decision")
        row = self.catalog.place(
            object_code=obj.object_code,
            collection=obj.collection,
            title=obj.title,
            accepted_by=obj.accepted_by,
            object_type=obj.object_type,
            body=obj.body_or_uri,
            tags=obj.tags,
            version=(obj.version, obj.version_minor),
            capture_channel=obj.capture_channel,
        )
        placed = self._with_prior_link(object_from_row(row, self.catalog.tags(obj.object_code)))
        obj.version_minor = placed.version_minor
        obj.object_type = placed.object_type
        obj.lifecycle_state = placed.lifecycle_state
        obj.library_object_id = placed.library_object_id
        obj.supersedes_version = placed.supersedes_version
        return obj

    def _with_prior_link(self, obj: LibraryObject) -> LibraryObject:
        history = self.catalog.version_rows(obj.object_code)
        by_id = {r["version_id"]: r for r in history}
        for row in history:
            if row["version_major"] == obj.version and row["version_minor"] == obj.version_minor:
                prior = by_id.get(row["supersedes_version_id"])
                obj.supersedes_version = prior["version_major"] if prior else None
        return obj

    def next_version(self, object_code: str) -> int:
        history = self.catalog.version_rows(object_code)
        return (max(r["version_major"] for r in history) + 1) if history else 1

    def history(self, object_code: str) -> List[LibraryObject]:
        rows = self.catalog.version_rows(object_code)
        tags = self.catalog.tags(object_code)
        by_id = {r["version_id"]: r for r in rows}
        result = []
        for row in rows:
            obj = object_from_row(row, tags)
            prior = by_id.get(row["supersedes_version_id"])
            obj.supersedes_version = prior["version_major"] if prior else None
            result.append(obj)
        return result

    def get_version(self, object_code: str, version: int) -> Optional[LibraryObject]:
        for obj in self.history(object_code):
            if obj.version == version and obj.version_minor == 0:
                return obj
        return None

    def all_object_codes(self) -> List[str]:
        return self.catalog.all_object_codes()
