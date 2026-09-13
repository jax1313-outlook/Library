"""Candidate intake from Intelligence, into the durable queue.

The Intelligence repository's `dispatch_intel.service.route_to_library(finding, ..., store=...)`
builds a `LibraryCandidate` and, when given a store, makes exactly one call on it:
`store.save_library_candidate(candidate)`. `DurableCandidateSink` answers that call by
submitting the candidate to the Library catalog. So Intelligence routes into the durable queue
by passing this object as its store:

    from dispatch_intel.service import route_to_library
    route_to_library(finding, store=DurableCandidateSink(library))

No code is shared between the repositories and neither imports the other. The candidate keeps
its own id and creation time, so a candidate Intelligence traced is the same one Library holds,
across any number of process restarts.

The sink only receives. It does not classify, confirm, validate or approve: those are Library's
and a person's steps, and they happen on the catalog, not in Intelligence's call.
"""
from __future__ import annotations

from typing import List

from dispatch_library.models import LibraryCandidate


class DurableCandidateSink:
    def __init__(self, library) -> None:
        self.library = library
        self.received: List[str] = []

    def save_library_candidate(self, candidate) -> LibraryCandidate:
        stored = self.library.submit_candidate(candidate)
        self.received.append(stored.candidate_id)
        return stored

    def list_library_candidates(self) -> List[LibraryCandidate]:
        return [c for c in self.library.candidate_queue.all() if c.candidate_id in set(self.received)]
