import pytest

from dispatch_library.ingestion import CandidateQueue, ingest_human_document, review_candidate, submit_candidate
from dispatch_library.models import LibraryCandidate, LibraryCandidateStatus, LibraryObjectSource, LibraryObjectStatus, SubmittedBy
from dispatch_library.registry import ObjectRegistry


def test_human_ingestion_is_immediately_current_no_second_gate():
    registry = ObjectRegistry()
    obj = ingest_human_document(
        registry,
        object_code="SOP-001",
        collection="Process",
        title="Load Intake SOP",
        body_or_uri="body text",
        accepted_by="Mike Zachary",
    )

    assert obj.status == LibraryObjectStatus.CURRENT
    assert obj.source == LibraryObjectSource.HUMAN_PLACED
    # No "pending" or "draft" intermediate state exists for a human-placed document.
    assert obj.version == 1


def test_human_ingestion_rejects_system_identity_as_accepted_by():
    registry = ObjectRegistry()
    with pytest.raises(ValueError):
        ingest_human_document(
            registry,
            object_code="SOP-002",
            collection="Process",
            title="Test",
            body_or_uri="body",
            accepted_by="LIBRARY",
        )


def test_reingesting_same_object_code_supersedes_previous_version():
    registry = ObjectRegistry()
    ingest_human_document(registry, "SOP-001", "Process", "v1", "body v1", "Mike Zachary")
    v2 = ingest_human_document(registry, "SOP-001", "Process", "v2", "body v2", "Mike Zachary")

    assert v2.version == 2
    history = registry.history("SOP-001")
    assert history[0].status == LibraryObjectStatus.SUPERSEDED
    assert history[1].status == LibraryObjectStatus.CURRENT


def _candidate(**overrides):
    kwargs = dict(
        submitted_by=SubmittedBy.INTELLIGENCE,
        source_type="Load board opportunity",
        collection="Route_Intelligence",
        proposed_object_code="CAND-001",
        proposed_title="Recurring Jacksonville-Savannah run",
        proposed_body_or_reference="pointer to finding",
    )
    kwargs.update(overrides)
    return LibraryCandidate(**kwargs)


def test_candidate_starts_pending_review_not_truth():
    registry = ObjectRegistry()
    queue = CandidateQueue()
    candidate = submit_candidate(queue, _candidate())

    assert candidate.status == LibraryCandidateStatus.PENDING_REVIEW
    from dispatch_library.resolver import current
    assert current(registry, "CAND-001") is None


def test_candidate_cannot_approve_itself():
    registry = ObjectRegistry()
    queue = CandidateQueue()
    candidate = submit_candidate(queue, _candidate())

    with pytest.raises(ValueError):
        review_candidate(queue, registry, candidate.candidate_id, approve=True, reviewed_by="INTELLIGENCE")

    with pytest.raises(ValueError):
        review_candidate(queue, registry, candidate.candidate_id, approve=True, reviewed_by="SYSTEM")


def test_approved_candidate_becomes_current_library_truth():
    registry = ObjectRegistry()
    queue = CandidateQueue()
    candidate = submit_candidate(queue, _candidate())

    reviewed = review_candidate(queue, registry, candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")
    assert reviewed.status == LibraryCandidateStatus.APPROVED
    assert reviewed.reviewed_by == "Mike Zachary"

    from dispatch_library.resolver import current
    obj = current(registry, "CAND-001")
    assert obj is not None
    assert obj.source.value == "APPROVED_CANDIDATE"


def test_rejected_candidate_never_becomes_library_truth():
    registry = ObjectRegistry()
    queue = CandidateQueue()
    candidate = submit_candidate(queue, _candidate(proposed_object_code="CAND-002"))

    reviewed = review_candidate(queue, registry, candidate.candidate_id, approve=False, reviewed_by="Mike Zachary")
    assert reviewed.status == LibraryCandidateStatus.REJECTED

    from dispatch_library.resolver import current
    assert current(registry, "CAND-002") is None


def test_candidate_cannot_be_reviewed_twice():
    registry = ObjectRegistry()
    queue = CandidateQueue()
    candidate = submit_candidate(queue, _candidate(proposed_object_code="CAND-003"))
    review_candidate(queue, registry, candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")

    with pytest.raises(ValueError):
        review_candidate(queue, registry, candidate.candidate_id, approve=False, reviewed_by="Mike Zachary")
