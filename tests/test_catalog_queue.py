"""The Candidate Queue, and what durability is actually for.

A candidate is a nomination waiting for a person. The wait is measured in days;
the process is not. A queue that empties on exit cannot hold one, which is
another way of saying an Intelligence finding routed to Library did not survive
being routed.

Every approval rule is still `ingestion.review_candidate()`'s own. These tests
prove the rules survive the move to disk rather than restating them.
"""
from __future__ import annotations

import sqlite3

import pytest

from dispatch_library import ingestion, resolver
from dispatch_library.catalog import library, open_library
from dispatch_library.models import (
    LibraryCandidate,
    LibraryCandidateStatus,
    LibraryObjectSource,
    SubmittedBy,
)


def _candidate(**overrides) -> LibraryCandidate:
    kwargs = dict(
        submitted_by=SubmittedBy.INTELLIGENCE,
        source_type="finding",
        collection="Reference",
        proposed_object_code="DOC-FROM-INTEL",
        proposed_title="Something worth keeping",
        proposed_body_or_reference="body",
        source_finding_id="FIND-1",
    )
    kwargs.update(overrides)
    return LibraryCandidate(**kwargs)


@pytest.fixture()
def lib(tmp_path):
    with library(tmp_path / "catalog.db") as service:
        yield service


class TestTheQueueHoldsNominations:
    def test_a_submitted_candidate_is_pending(self, lib):
        candidate = lib.submit_candidate(_candidate())
        assert candidate.status == LibraryCandidateStatus.PENDING_REVIEW
        assert [c.candidate_id for c in lib.pending_candidates()] == [candidate.candidate_id]

    def test_a_candidate_can_be_fetched_by_id(self, lib):
        candidate = lib.submit_candidate(_candidate())
        fetched = lib.candidate_queue.get(candidate.candidate_id)
        assert fetched.proposed_object_code == "DOC-FROM-INTEL"
        assert fetched.source_finding_id == "FIND-1"

    def test_an_unknown_id_is_none_not_an_error(self, lib):
        assert lib.candidate_queue.get("no-such-candidate") is None

    def test_pending_is_oldest_first(self, lib):
        """A work queue. The nomination waiting longest is the one most likely
        to be forgotten, so it is the one that shows up first."""
        for index in range(3):
            lib.submit_candidate(_candidate(
                proposed_object_code=f"DOC-{index}",
                created_at=f"2026-09-0{index + 1}T00:00:00+00:00",
            ))
        assert [c.proposed_object_code for c in lib.pending_candidates()] == [
            "DOC-0", "DOC-1", "DOC-2"
        ]

    def test_all_includes_the_reviewed_ones(self, lib):
        approved = lib.submit_candidate(_candidate(proposed_object_code="DOC-A"))
        lib.submit_candidate(_candidate(proposed_object_code="DOC-B"))
        lib.review_candidate(approved.candidate_id, approve=True, reviewed_by="Mike Zachary")

        assert len(lib.candidate_queue.all()) == 2
        assert len(lib.pending_candidates()) == 1

    def test_two_gets_return_the_same_handle(self, lib):
        """Two different objects for one candidate would let a caller review
        one and persist the other."""
        candidate = lib.submit_candidate(_candidate())
        first = lib.candidate_queue.get(candidate.candidate_id)
        second = lib.candidate_queue.get(candidate.candidate_id)
        assert first is second


class TestReviewPlacesTheObject:
    def test_approving_places_it_in_the_library(self, lib):
        candidate = lib.submit_candidate(_candidate())
        lib.review_candidate(candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")

        placed = lib.current("DOC-FROM-INTEL")
        assert placed is not None
        assert placed.source == LibraryObjectSource.APPROVED_CANDIDATE
        assert placed.accepted_by == "Mike Zachary"
        assert placed.version == 1

    def test_rejecting_places_nothing(self, lib):
        candidate = lib.submit_candidate(_candidate())
        reviewed = lib.review_candidate(
            candidate.candidate_id, approve=False, reviewed_by="Mike Zachary"
        )
        assert reviewed.status == LibraryCandidateStatus.REJECTED
        assert lib.current("DOC-FROM-INTEL") is None

    def test_approving_a_second_time_makes_version_two(self, lib):
        for body in ("first", "second"):
            candidate = lib.submit_candidate(_candidate(proposed_body_or_reference=body))
            lib.review_candidate(candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")

        assert lib.current("DOC-FROM-INTEL").version == 2
        assert lib.current("DOC-FROM-INTEL").body_or_uri == "second"


class TestTheApprovalRulesSurviveTheMoveToDisk:
    """Each of these is `ingestion.review_candidate()` refusing. The point is
    that persistence did not create a way around any of them."""

    def test_a_system_identity_may_not_review(self, lib):
        candidate = lib.submit_candidate(_candidate())
        with pytest.raises(ValueError, match="not a system identity"):
            lib.review_candidate(candidate.candidate_id, approve=True, reviewed_by="LIBRARY")

    @pytest.mark.parametrize("submitter", [SubmittedBy.PUBLISHER, SubmittedBy.INTELLIGENCE])
    def test_a_submitter_may_not_approve_its_own_nomination(self, lib, submitter):
        """Refused -- by the system-identity rule, which catches it first.

        `ingestion.review_candidate()` also has an explicit
        `reviewed_by == submitted_by` check after this one. Both values
        `SubmittedBy` can hold are in RESERVED_SYSTEM_IDENTITIES, so that second
        check cannot currently fire: the first one always gets there. It is
        harmless defence in depth and worth keeping -- if the reserved set ever
        narrows, it becomes the rule that holds. Noted here so the next person
        reading it does not conclude the test is missing.
        """
        candidate = lib.submit_candidate(_candidate(submitted_by=submitter))
        with pytest.raises(ValueError, match="not a system identity"):
            lib.review_candidate(
                candidate.candidate_id, approve=True, reviewed_by=submitter.value
            )

    def test_an_unknown_candidate_is_refused(self, lib):
        with pytest.raises(ValueError, match="no candidate"):
            lib.review_candidate("no-such-candidate", approve=True, reviewed_by="Mike Zachary")

    def test_a_candidate_may_not_be_reviewed_twice(self, lib):
        candidate = lib.submit_candidate(_candidate())
        lib.review_candidate(candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")
        with pytest.raises(ValueError, match="already reviewed"):
            lib.review_candidate(candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")

    def test_a_refused_review_writes_nothing_at_all(self, lib):
        """The refusal happens before any write, and the transaction rolls
        back. The candidate must still be pending afterwards -- a nomination
        marked reviewed by a refused review would be unreachable forever."""
        candidate = lib.submit_candidate(_candidate())
        with pytest.raises(ValueError):
            lib.review_candidate(candidate.candidate_id, approve=True, reviewed_by="SYSTEM")

        assert len(lib.pending_candidates()) == 1
        assert lib.current("DOC-FROM-INTEL") is None

    def test_an_invalid_collection_is_refused_at_construction(self):
        with pytest.raises(ValueError, match="not one of the 15"):
            _candidate(collection="Invented")


class TestItSurvivesTheProcess:
    def test_a_pending_candidate_is_still_there_after_a_restart(self, tmp_path):
        path = tmp_path / "catalog.db"

        with library(path) as first:
            candidate = first.submit_candidate(_candidate())
            candidate_id = candidate.candidate_id

        with library(path) as second:
            pending = second.pending_candidates()
            assert len(pending) == 1
            assert pending[0].candidate_id == candidate_id
            assert pending[0].proposed_title == "Something worth keeping"
            assert pending[0].source_finding_id == "FIND-1"

    def test_it_can_be_reviewed_by_a_later_process(self, tmp_path):
        """The nomination waits for a person, not for a process. This is the
        whole reason the queue moved to disk."""
        path = tmp_path / "catalog.db"

        with library(path) as first:
            candidate_id = first.submit_candidate(_candidate()).candidate_id

        with library(path) as second:
            second.review_candidate(candidate_id, approve=True, reviewed_by="Mike Zachary")

        with library(path) as third:
            assert third.pending_candidates() == []
            placed = third.current("DOC-FROM-INTEL")
            assert placed is not None
            assert placed.accepted_by == "Mike Zachary"
            reviewed = third.candidate_queue.get(candidate_id)
            assert reviewed.status == LibraryCandidateStatus.APPROVED
            assert reviewed.reviewed_by == "Mike Zachary"
            assert reviewed.reviewed_at is not None

    def test_a_rejection_is_remembered_too(self, tmp_path):
        """A rejected nomination that came back as pending would be re-reviewed
        forever, and the reviewer's decision would count for nothing."""
        path = tmp_path / "catalog.db"

        with library(path) as first:
            candidate_id = first.submit_candidate(_candidate()).candidate_id
            first.review_candidate(candidate_id, approve=False, reviewed_by="Mike Zachary")

        with library(path) as second:
            assert second.pending_candidates() == []
            assert second.candidate_queue.get(candidate_id).status == (
                LibraryCandidateStatus.REJECTED
            )

    def test_an_in_memory_library_forgets_and_says_so(self):
        """`open_library()` with no path is the full machinery and nothing on
        disk. It is honest about being a dict with extra steps."""
        first = open_library()
        first.submit_candidate(_candidate())
        assert len(first.pending_candidates()) == 1
        first.close()

        second = open_library()
        assert second.pending_candidates() == []
        second.close()


class TestAnApprovalIsOneTransaction:
    def test_the_candidate_and_its_object_commit_together(self, tmp_path):
        """A catalog holding an approved candidate whose object never arrived
        has lost a document and recorded that it accepted one.

        The object write is blocked with a trigger rather than a contrived
        collision, because what matters is that *any* failure during the object
        write takes the candidate's status down with it -- not one particular
        failure.
        """
        path = tmp_path / "catalog.db"

        with library(path) as lib:
            candidate_id = lib.submit_candidate(_candidate()).candidate_id
            lib.connection.executescript(
                "CREATE TRIGGER block_the_object_write "
                "BEFORE INSERT ON library_object "
                "WHEN NEW.object_code = 'DOC-FROM-INTEL' "
                "BEGIN SELECT RAISE(ABORT, 'the object write failed'); END;"
            )

            with pytest.raises(sqlite3.IntegrityError):
                lib.review_candidate(candidate_id, approve=True, reviewed_by="Mike Zachary")

            # Still pending. If the flush had committed without the object
            # write, this nomination would read as approved with nothing to
            # show for it -- and no one would ever look at it again.
            still_pending = lib.pending_candidates()
            assert len(still_pending) == 1
            assert still_pending[0].candidate_id == candidate_id
            assert lib.current("DOC-FROM-INTEL") is None

            lib.connection.executescript("DROP TRIGGER block_the_object_write")

        # And it is genuinely still reviewable afterwards.
        with library(path) as reopened:
            reopened.review_candidate(candidate_id, approve=True, reviewed_by="Mike Zachary")
            assert reopened.current("DOC-FROM-INTEL") is not None

    def test_the_rollback_survives_a_restart(self, tmp_path):
        """Rolled back in the catalog, not just in the objects held in memory."""
        path = tmp_path / "catalog.db"

        with library(path) as lib:
            candidate_id = lib.submit_candidate(_candidate()).candidate_id
            with pytest.raises(ValueError):
                lib.review_candidate(candidate_id, approve=True, reviewed_by="SYSTEM")

        with library(path) as reopened:
            assert len(reopened.pending_candidates()) == 1
            assert reopened.candidate_queue.get(candidate_id).status == (
                LibraryCandidateStatus.PENDING_REVIEW
            )
            assert reopened.candidate_queue.get(candidate_id).reviewed_by is None


class TestTheDictQueueStillWorks:
    """`ingestion.CandidateQueue` is unchanged and stays the no-file option."""

    def test_the_original_queue_behaves_as_it_always_did(self):
        queue = ingestion.CandidateQueue()
        from dispatch_library.registry import ObjectRegistry

        registry = ObjectRegistry()
        candidate = ingestion.submit_candidate(queue, _candidate())
        assert len(queue.pending()) == 1

        ingestion.review_candidate(
            queue, registry, candidate.candidate_id, approve=True, reviewed_by="Mike Zachary"
        )
        assert queue.pending() == []
        assert resolver.current(registry, "DOC-FROM-INTEL") is not None
