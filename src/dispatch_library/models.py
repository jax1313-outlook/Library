"""
Object model for the Library department.

Schemas here MUST match DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md (Claude-3 repo), Sections 3.5 and
4, field-for-field — in particular `LibraryCandidate` mirrors the Intelligence repo's dataclass of
the same name exactly, because a candidate object crosses the repo boundary from Intelligence (or
Publisher) into Library without a shared package dependency. Field-name discipline is what keeps
the two repos compatible.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from dispatch_library.taxonomy import require_valid_collection


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _asdict(obj: Any) -> Dict[str, Any]:
    def _convert(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, list):
            return [_convert(v) for v in value]
        if dataclasses.is_dataclass(value):
            return _asdict(value)
        return value

    return {f.name: _convert(getattr(obj, f.name)) for f in dataclasses.fields(obj)}


class LibraryObjectStatus(str, Enum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    DRAFT_CANDIDATE = "DRAFT_CANDIDATE"


class LibraryObjectSource(str, Enum):
    HUMAN_PLACED = "HUMAN_PLACED"
    APPROVED_CANDIDATE = "APPROVED_CANDIDATE"


class LibraryCandidateStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SubmittedBy(str, Enum):
    INTELLIGENCE = "INTELLIGENCE"
    PUBLISHER = "PUBLISHER"


class RecipeType(str, Enum):
    BROKER_ONBOARDING_PACKET = "BROKER_ONBOARDING_PACKET"
    GOVERNMENT_PROPOSAL_PACKET = "GOVERNMENT_PROPOSAL_PACKET"
    VISIBILITY_STATUS_PACKET = "VISIBILITY_STATUS_PACKET"
    POD_PACKAGE = "POD_PACKAGE"
    REVIEW_PACKAGE = "REVIEW_PACKAGE"


class RecipeStatus(str, Enum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"


# System-identity strings that may never be used as a human approver identity. Prevents a
# submitting system from approving its own candidate under a slightly different label.
RESERVED_SYSTEM_IDENTITIES = {"INTELLIGENCE", "PUBLISHER", "LIBRARY", "SYSTEM", "AUTOMATION"}


@dataclasses.dataclass
class LibraryObject:
    object_code: str
    collection: str
    title: str
    version: int
    status: LibraryObjectStatus
    source: LibraryObjectSource
    body_or_uri: str
    accepted_by: str
    accepted_at: str = dataclasses.field(default_factory=_now)
    supersedes_version: Optional[int] = None
    tags: List[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        require_valid_collection(self.collection)
        if not self.accepted_by or self.accepted_by.strip().upper() in RESERVED_SYSTEM_IDENTITIES:
            raise ValueError(
                "accepted_by must identify a real human or approved-workflow reviewer, "
                "not a system identity (Hard Rule: no authority bypass)"
            )

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclasses.dataclass
class LibraryCandidate:
    submitted_by: SubmittedBy
    source_type: str
    collection: str
    proposed_object_code: str
    proposed_title: str
    proposed_body_or_reference: str
    source_finding_id: Optional[str] = None
    status: LibraryCandidateStatus = LibraryCandidateStatus.PENDING_REVIEW
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    candidate_id: str = dataclasses.field(default_factory=_new_id)
    created_at: str = dataclasses.field(default_factory=_now)

    def __post_init__(self) -> None:
        require_valid_collection(self.collection)

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


@dataclasses.dataclass
class PublisherRecipe:
    recipe_code: str
    recipe_type: RecipeType
    version: int
    required_library_object_codes: List[str] = dataclasses.field(default_factory=list)
    required_publisher_parts: List[str] = dataclasses.field(default_factory=list)
    required_intelligence_requirement_types: List[str] = dataclasses.field(default_factory=list)
    status: RecipeStatus = RecipeStatus.CURRENT

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)
