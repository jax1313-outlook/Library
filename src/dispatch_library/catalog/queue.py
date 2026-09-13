"""`SqliteCandidateQueue` -- the Library Candidate Queue surface over catalog schema version 2.

Same four methods as `ingestion.CandidateQueue`: `add`, `get`, `pending`, `all`. The queue is
durable: a nomination waits days for a person, and a queue that empties when the process exits
cannot hold one.

`pending()` means *awaiting a person*: PENDING_REVIEW and VALIDATED. A VALIDATED candidate has
passed Library's checks and still waits for the human decision.
"""
from __future__ import annotations

from typing import List, Optional

from dispatch_library.catalog.store import Catalog
from dispatch_library.models import LibraryCandidate, LibraryCandidateStatus, SubmittedBy


def candidate_from_row(row) -> LibraryCandidate:
    return LibraryCandidate(
        submitted_by=SubmittedBy(row["submitted_by_role"]),
        source_type=row["source_type"],
        collection=row["proposed_collection_id"],
        proposed_object_code=row["proposed_object_code"],
        proposed_title=row["proposed_title"],
        proposed_body_or_reference=row["proposed_body_or_reference"],
        source_finding_id=row["source_finding_id"],
        status=LibraryCandidateStatus(row["status"]),
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        candidate_id=row["candidate_id"],
        created_at=row["created_at"],
        submitted_by_name=row["submitted_by_name"],
        mission_record_id=row["mission_record_id"],
        workflow_event_id=row["workflow_event_id"],
        recommended_object_type=row["recommended_object_type"],
        proposed_object_type=row["proposed_object_type"],
        object_type_confirmed_by=row["object_type_confirmed_by"],
        object_type_confirmed_at=row["object_type_confirmed_at"],
        validation_result=row["validation_result"],
        validated_at=row["validated_at"],
    )


def _field(candidate, name, default=None):
    value = getattr(candidate, name, default)
    return getattr(value, "value", value)


def submit_from_contract(catalog: Catalog, candidate) -> LibraryCandidate:
    """Enter any object carrying the shared-contract candidate fields.

    Accepts this repository's `LibraryCandidate` or the Intelligence repository's
    `dispatch_intel.models.LibraryCandidate` -- the twelve fields are identical by contract,
    and nothing here imports the other repository. The candidate's own id and creation time
    are kept, so a candidate traced in Intelligence is the same candidate here.
    """
    status = _field(candidate, "status", "PENDING_REVIEW")
    if status not in ("PENDING_REVIEW", "SUBMITTED"):
        raise ValueError("newly submitted candidates must be PENDING_REVIEW")
    row = catalog.submit_candidate(
        submitted_by_role=_field(candidate, "submitted_by"),
        source_type=_field(candidate, "source_type"),
        collection=_field(candidate, "collection"),
        proposed_object_code=_field(candidate, "proposed_object_code"),
        proposed_title=_field(candidate, "proposed_title"),
        proposed_body_or_reference=_field(candidate, "proposed_body_or_reference"),
        source_finding_id=_field(candidate, "source_finding_id"),
        submitted_by_name=_field(candidate, "submitted_by_name"),
        mission_record_id=_field(candidate, "mission_record_id"),
        workflow_event_id=_field(candidate, "workflow_event_id"),
        proposed_object_type=_field(candidate, "proposed_object_type"),
        candidate_id=_field(candidate, "candidate_id"),
        created_at=_field(candidate, "created_at"),
    )
    return candidate_from_row(row)


class SqliteCandidateQueue:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def add(self, candidate) -> LibraryCandidate:
        return submit_from_contract(self.catalog, candidate)

    def get(self, candidate_id: str) -> Optional[LibraryCandidate]:
        row = self.catalog.candidate_row(candidate_id)
        return candidate_from_row(row) if row else None

    def pending(self) -> List[LibraryCandidate]:
        return [candidate_from_row(r) for r in self.catalog.candidates(("PENDING_REVIEW", "VALIDATED"))]

    def all(self) -> List[LibraryCandidate]:
        return [candidate_from_row(r) for r in self.catalog.candidates()]
