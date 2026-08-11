import pytest

from dispatch_library.models import LibraryCandidate, RecipeType, SubmittedBy
from dispatch_library.service import LibraryService


def test_service_ingest_and_current_round_trip():
    service = LibraryService()
    service.ingest_human_document(
        object_code="SOP-001",
        collection="Process",
        title="Intake SOP",
        body_or_uri="body",
        accepted_by="Mike Zachary",
    )
    obj = service.current("SOP-001")
    assert obj is not None
    assert obj.title == "Intake SOP"


def test_service_candidate_lifecycle_requires_external_approval():
    service = LibraryService()
    candidate = LibraryCandidate(
        submitted_by=SubmittedBy.PUBLISHER,
        source_type="Draft Review Package",
        collection="Templates",
        proposed_object_code="TPL-001",
        proposed_title="Broker Onboarding Cover Letter",
        proposed_body_or_reference="pointer to review package",
    )
    service.submit_candidate(candidate)
    assert service.current("TPL-001") is None
    assert len(service.pending_candidates()) == 1

    with pytest.raises(ValueError):
        service.review_candidate(candidate.candidate_id, approve=True, reviewed_by="PUBLISHER")

    service.review_candidate(candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")
    assert service.current("TPL-001") is not None
    assert len(service.pending_candidates()) == 0


def test_service_resolve_packet_uses_registered_recipe():
    service = LibraryService()
    service.ingest_human_document("COI-TEMPLATE", "Templates", "COI", "body", "Mike Zachary")
    from dispatch_library.models import PublisherRecipe

    service.register_recipe(
        PublisherRecipe(
            recipe_code="RECIPE-BROKER-v2",
            recipe_type=RecipeType.BROKER_ONBOARDING_PACKET,
            version=2,
            required_library_object_codes=["COI-TEMPLATE", "W9-TEMPLATE"],
        )
    )

    resolved = service.resolve_packet(RecipeType.BROKER_ONBOARDING_PACKET)
    assert resolved["COI-TEMPLATE"] is not None and resolved["COI-TEMPLATE"] != "MISSING"
    assert resolved["W9-TEMPLATE"] == "MISSING"
