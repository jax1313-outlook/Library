"""
Two acceptance paths into Library truth, per DISPATCH_CONSTITUTION_v3.md Section 7.4 and
04_DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md Hard Rules / Forbidden Movements:

1. `ingest_human_document` — a human places a document directly into Library. It becomes CURRENT
   immediately. No additional validation loop is created (Forbidden Movement: "Human-Placed
   Library Asset -> Artificial Validation Loop"). The human's identity (`accepted_by`) IS the
   approval; there is no second gate.

2. `submit_candidate` / `review_candidate` — Intelligence or Publisher nominates a Library
   Candidate. It starts PENDING_REVIEW and can only become Library truth through an explicit
   `review_candidate(..., approve=True, reviewed_by=<human>)` call (Forbidden Movement:
   "Intelligence Finding -> Library Truth Automatically"). A candidate can never approve itself:
   `reviewed_by` may not be a system identity (enforced in `models.LibraryObject.__post_init__`
   and re-checked here).
"""
from __future__ import annotations

from typing import List, Optional

from dispatch_library.models import (
    LibraryCandidate,
    LibraryCandidateStatus,
    LibraryObject,
    LibraryObjectSource,
    LibraryObjectStatus,
    RESERVED_SYSTEM_IDENTITIES,
    _now,
)
from dispatch_library.registry import ObjectRegistry


class CandidateQueue:
    """Library Candidate Queue — holds nominations pending human review."""

    def __init__(self) -> None:
        self._candidates: dict[str, LibraryCandidate] = {}

    def add(self, candidate: LibraryCandidate) -> LibraryCandidate:
        self._candidates[candidate.candidate_id] = candidate
        return candidate

    def get(self, candidate_id: str) -> Optional[LibraryCandidate]:
        return self._candidates.get(candidate_id)

    def pending(self) -> List[LibraryCandidate]:
        return [c for c in self._candidates.values() if c.status == LibraryCandidateStatus.PENDING_REVIEW]

    def all(self) -> List[LibraryCandidate]:
        return list(self._candidates.values())


def ingest_human_document(
    registry: ObjectRegistry,
    object_code: str,
    collection: str,
    title: str,
    body_or_uri: str,
    accepted_by: str,
    tags: Optional[List[str]] = None,
) -> LibraryObject:
    version = registry.next_version(object_code)
    obj = LibraryObject(
        object_code=object_code,
        collection=collection,
        title=title,
        version=version,
        status=LibraryObjectStatus.CURRENT,
        source=LibraryObjectSource.HUMAN_PLACED,
        body_or_uri=body_or_uri,
        accepted_by=accepted_by,
        supersedes_version=(version - 1) if version > 1 else None,
        tags=list(tags or []),
    )
    return registry.add_version(obj)


def submit_candidate(queue: CandidateQueue, candidate: LibraryCandidate) -> LibraryCandidate:
    if candidate.status != LibraryCandidateStatus.PENDING_REVIEW:
        raise ValueError("newly submitted candidates must be PENDING_REVIEW")
    return queue.add(candidate)


def review_candidate(
    queue: CandidateQueue,
    registry: ObjectRegistry,
    candidate_id: str,
    approve: bool,
    reviewed_by: str,
) -> LibraryCandidate:
    candidate = queue.get(candidate_id)
    if candidate is None:
        raise ValueError(f"no candidate {candidate_id!r} in queue")
    if candidate.status != LibraryCandidateStatus.PENDING_REVIEW:
        raise ValueError(f"candidate {candidate_id!r} already reviewed (status={candidate.status})")
    if not reviewed_by or reviewed_by.strip().upper() in RESERVED_SYSTEM_IDENTITIES:
        raise ValueError(
            "reviewed_by must identify a real human or approved-workflow reviewer, "
            "not a system identity (Hard Rule: Publisher/Intelligence may not approve themselves)"
        )
    if reviewed_by.strip().upper() == candidate.submitted_by.value:
        raise ValueError("reviewed_by must not equal the submitting system's own identity")

    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = _now()
    candidate.status = LibraryCandidateStatus.APPROVED if approve else LibraryCandidateStatus.REJECTED

    if approve:
        version = registry.next_version(candidate.proposed_object_code)
        obj = LibraryObject(
            object_code=candidate.proposed_object_code,
            collection=candidate.collection,
            title=candidate.proposed_title,
            version=version,
            status=LibraryObjectStatus.CURRENT,
            source=LibraryObjectSource.APPROVED_CANDIDATE,
            body_or_uri=candidate.proposed_body_or_reference,
            accepted_by=reviewed_by,
            supersedes_version=(version - 1) if version > 1 else None,
        )
        registry.add_version(obj)

    return candidate
