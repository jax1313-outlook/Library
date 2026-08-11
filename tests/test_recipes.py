from dispatch_library.ingestion import ingest_human_document
from dispatch_library.models import LibraryObjectStatus, PublisherRecipe, RecipeStatus, RecipeType
from dispatch_library.recipes import MISSING, RecipeRegistry, default_recipe_registry, resolve_packet
from dispatch_library.registry import ObjectRegistry


def test_default_recipe_registry_has_five_doctrine_named_types():
    registry = default_recipe_registry()
    types = {r.recipe_type for r in registry.all()}
    assert types == {
        RecipeType.BROKER_ONBOARDING_PACKET,
        RecipeType.GOVERNMENT_PROPOSAL_PACKET,
        RecipeType.VISIBILITY_STATUS_PACKET,
        RecipeType.POD_PACKAGE,
        RecipeType.REVIEW_PACKAGE,
    }


def test_resolve_packet_reports_missing_items_not_fabricated():
    obj_registry = ObjectRegistry()
    recipe_registry = RecipeRegistry()
    recipe_registry.register(
        PublisherRecipe(
            recipe_code="RECIPE-TEST-v1",
            recipe_type=RecipeType.BROKER_ONBOARDING_PACKET,
            version=1,
            required_library_object_codes=["W9-TEMPLATE", "COI-TEMPLATE"],
        )
    )

    resolved = resolve_packet(obj_registry, recipe_registry, RecipeType.BROKER_ONBOARDING_PACKET)
    assert resolved["W9-TEMPLATE"] == MISSING
    assert resolved["COI-TEMPLATE"] == MISSING


def test_resolve_packet_returns_current_object_when_present():
    obj_registry = ObjectRegistry()
    ingest_human_document(obj_registry, "W9-TEMPLATE", "Templates", "W9", "body", "Mike Zachary")

    recipe_registry = RecipeRegistry()
    recipe_registry.register(
        PublisherRecipe(
            recipe_code="RECIPE-TEST-v1",
            recipe_type=RecipeType.BROKER_ONBOARDING_PACKET,
            version=1,
            required_library_object_codes=["W9-TEMPLATE"],
        )
    )

    resolved = resolve_packet(obj_registry, recipe_registry, RecipeType.BROKER_ONBOARDING_PACKET)
    assert resolved["W9-TEMPLATE"] != MISSING
    assert resolved["W9-TEMPLATE"].status == LibraryObjectStatus.CURRENT


def test_registering_new_recipe_version_supersedes_old_one():
    registry = RecipeRegistry()
    v1 = registry.register(
        PublisherRecipe(recipe_code="R-v1", recipe_type=RecipeType.POD_PACKAGE, version=1)
    )
    v2 = registry.register(
        PublisherRecipe(recipe_code="R-v2", recipe_type=RecipeType.POD_PACKAGE, version=2)
    )

    assert v1.status == RecipeStatus.SUPERSEDED
    assert v2.status == RecipeStatus.CURRENT
    assert registry.get_current(RecipeType.POD_PACKAGE).recipe_code == "R-v2"


def test_unregistered_recipe_type_resolves_empty():
    obj_registry = ObjectRegistry()
    recipe_registry = RecipeRegistry()
    assert resolve_packet(obj_registry, recipe_registry, RecipeType.GOVERNMENT_PROPOSAL_PACKET) == {}
