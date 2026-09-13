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
    # Additive, plan v2 ruling 4: SUBMITTED -> PENDING_REVIEW -> VALIDATED -> APPROVED.
    # PENDING_REVIEW, APPROVED and REJECTED keep the names the Intelligence repo uses.
    SUBMITTED = "SUBMITTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class SubmittedBy(str, Enum):
    INTELLIGENCE = "INTELLIGENCE"
    PUBLISHER = "PUBLISHER"
    # Additive, plan v2 ruling 2. DISPATCH only with a Mission Record or workflow event.
    HUMAN = "HUMAN"
    DISPATCH = "DISPATCH"


class LifecycleState(str, Enum):
    """Where a version stands. CURRENT, ACTIVE_USE and REVIEW_DUE are all current."""

    CURRENT = "CURRENT"
    ACTIVE_USE = "ACTIVE_USE"
    REVIEW_DUE = "REVIEW_DUE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED_VERSION_RECORD = "ARCHIVED_VERSION_RECORD"
    RETENTION_REVIEW = "RETENTION_REVIEW"


CURRENT_STATES = frozenset({LifecycleState.CURRENT, LifecycleState.ACTIVE_USE, LifecycleState.REVIEW_DUE})

#: The eighteen object types of the Library Department Core Object Model, section 4.
OBJECT_TYPES = (
    "CONSTITUTION_PACKAGE", "AMENDMENT_CURRENT_RULE", "ROLE_DOCTRINE", "SOP_WORKFLOW",
    "OPERATIONAL_INSTRUCTION", "COMPLIANCE_ASSET", "CONTROLLED_COMPANY_FACT",
    "COMPANY_CREDENTIAL", "CAPABILITY_ASSET", "PAST_PERFORMANCE_REFERENCE",
    "RATE_SHEET_PRICING_TEMPLATE", "PACKET", "PACKET_COMPONENT", "FORM_TEMPLATE",
    "TRAINING_ASSET_MANUAL", "APPLIED_LESSON_PACKAGE", "VALIDATED_INTELLIGENCE_SUMMARY",
    "LIBRARY_INDEX_MANIFEST",
)


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
# JOE, DISPATCH, COMI and EMAIL_HELPER added by plan v2 ruling 6. Joe may be recorded as the
# capture channel of an approval, never as the approver.
RESERVED_SYSTEM_IDENTITIES = {
    "INTELLIGENCE", "PUBLISHER", "LIBRARY", "JOE", "DISPATCH", "SYSTEM", "AUTOMATION", "COMI",
    "EMAIL_HELPER",
}


def normalize_identity(name: Optional[str]) -> str:
    """The comparison form of an identity: trimmed, upper case, spaces and hyphens as `_`.

    Mirrors the catalog schema's `replace(replace(upper(trim(x)),' ','_'),'-','_')` exactly, so
    `Email Helper` is refused here with a clear message rather than first by the database.
    """
    return (name or "").strip().upper().replace(" ", "_").replace("-", "_")


def is_reserved_identity(name: Optional[str]) -> bool:
    return normalize_identity(name) in RESERVED_SYSTEM_IDENTITIES


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
    # Additive, plan v2. Defaults keep every existing constructor working.
    version_minor: int = 0
    object_type: Optional[str] = None
    lifecycle_state: Optional[str] = None
    capture_channel: Optional[str] = None
    library_object_id: Optional[str] = None

    def __post_init__(self) -> None:
        require_valid_collection(self.collection)
        if not self.accepted_by or not self.accepted_by.strip() or is_reserved_identity(self.accepted_by):
            raise ValueError(
                "accepted_by must identify a real human or approved-workflow reviewer, "
                "not a system identity (Hard Rule: no authority bypass)"
            )
        if self.object_type is not None and self.object_type not in OBJECT_TYPES:
            raise ValueError(f"object_type {self.object_type!r} is not one of the Core Object Model types")

    @property
    def version_label(self) -> str:
        return f"{self.version}.{self.version_minor}"

    @property
    def blocked_for_external_use(self) -> bool:
        return self.lifecycle_state == LifecycleState.REVIEW_DUE.value

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
    # Additive, plan v2 rulings 2-5. The first twelve fields stay field-identical to
    # dispatch_intel.models.LibraryCandidate; everything below has a default.
    submitted_by_name: Optional[str] = None
    mission_record_id: Optional[str] = None
    workflow_event_id: Optional[str] = None
    recommended_object_type: Optional[str] = None
    proposed_object_type: Optional[str] = None
    object_type_confirmed_by: Optional[str] = None
    object_type_confirmed_at: Optional[str] = None
    validation_result: str = "NOT_RUN"
    validated_at: Optional[str] = None

    def __post_init__(self) -> None:
        require_valid_collection(self.collection)

    def to_dict(self) -> Dict[str, Any]:
        return _asdict(self)


#: The fields the Intelligence repository's LibraryCandidate carries, in its order.
INTELLIGENCE_CANDIDATE_FIELDS = (
    "submitted_by", "source_type", "collection", "proposed_object_code", "proposed_title",
    "proposed_body_or_reference", "source_finding_id", "status", "reviewed_by", "reviewed_at",
    "candidate_id", "created_at",
)


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
