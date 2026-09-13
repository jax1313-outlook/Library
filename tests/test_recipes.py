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


# --- publisher_recipes.json -------------------------------------------------------------------

import copy
import json
import os
from pathlib import Path

import pytest

from dispatch_library.recipes import load_recipe_registry, parse_publisher_recipes

# The shape of D:\Library\publisher_recipes.json as it stood on 2026-09-13. The real file is read
# by test_real_publisher_recipes_file_loads when it is on this machine.
SAMPLE = {
    "government_proposal": {
        "recipe_name": "Government Proposal Package",
        "recipe_type": "government_proposal",
        "required_company_items": ["company_profile", "w9", "sam_registration", "uei_cage",
                                   "sdvosb_certification", "insurance_certificate", "past_performance"],
        "required_publisher_items": ["technical_narrative_template", "past_performance_template",
                                     "submission_email_template", "compliance_checklist"],
        "required_human_items": ["pricing_sheet", "signed_required_forms"],
        "required_outputs": ["draft_technical_proposal", "draft_past_performance_volume",
                             "draft_submission_email", "human_review_checklist"],
        "human_review_required": True,
    },
    "broker_onboarding": {
        "recipe_name": "Broker Onboarding Packet",
        "recipe_type": "broker_onboarding",
        "required_company_items": ["w9", "insurance_certificate", "authority", "company_profile"],
        "required_publisher_items": ["broker_packet_template", "broker_introduction_email_template"],
        "required_human_items": ["broker_specific_forms"],
        "required_outputs": ["draft_broker_packet", "draft_introduction_email", "human_review_checklist"],
        "human_review_required": True,
    },
}

REAL_RECIPES = Path(os.environ.get("DISPATCH_PUBLISHER_RECIPES", r"D:\Library\publisher_recipes.json"))


def _write(tmp_path, data):
    path = tmp_path / "publisher_recipes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loaded_recipes_keep_every_field(tmp_path):
    registry = load_recipe_registry(_write(tmp_path, SAMPLE))

    for key, recipe_type in (("broker_onboarding", RecipeType.BROKER_ONBOARDING_PACKET),
                             ("government_proposal", RecipeType.GOVERNMENT_PROPOSAL_PACKET)):
        source = SAMPLE[key]
        recipe = registry.get_current(recipe_type)
        detail = registry.detail(recipe.recipe_code)
        assert recipe.required_library_object_codes == source["required_company_items"]
        assert recipe.required_publisher_parts == source["required_publisher_items"]
        assert recipe.required_intelligence_requirement_types == []
        assert detail.required_human_items == source["required_human_items"]
        assert detail.required_outputs == source["required_outputs"]
        assert detail.human_review_required is True
        assert detail.recipe_name == source["recipe_name"]
        assert detail.source_key == key


def test_types_without_a_source_stay_scaffold_and_say_so(tmp_path):
    registry = load_recipe_registry(_write(tmp_path, SAMPLE))

    assert registry.is_scaffold(RecipeType.BROKER_ONBOARDING_PACKET) is False
    assert registry.is_scaffold(RecipeType.GOVERNMENT_PROPOSAL_PACKET) is False
    for recipe_type in (RecipeType.VISIBILITY_STATUS_PACKET, RecipeType.POD_PACKAGE,
                        RecipeType.REVIEW_PACKAGE):
        assert registry.is_scaffold(recipe_type) is True
        assert registry.get_current(recipe_type).required_library_object_codes == []


def test_loading_creates_no_superseded_placeholder(tmp_path):
    registry = load_recipe_registry(_write(tmp_path, SAMPLE))
    assert len(registry.all()) == 5
    assert all(r.status == RecipeStatus.CURRENT for r in registry.all())


def test_loaded_recipe_resolves_every_company_item_missing_on_an_empty_shelf(tmp_path):
    registry = load_recipe_registry(_write(tmp_path, SAMPLE))
    resolved = resolve_packet(ObjectRegistry(), registry, RecipeType.BROKER_ONBOARDING_PACKET)
    assert resolved == {code: MISSING for code in SAMPLE["broker_onboarding"]["required_company_items"]}


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["broker_onboarding"].update(recipe_type="pod_package"), "does not match its key"),
    (lambda d: d.update(pod_package=dict(d["broker_onboarding"], recipe_type="pod_package")),
     "matches no doctrine recipe type"),
    (lambda d: d["broker_onboarding"].pop("required_outputs"), "required_outputs must be a list"),
    (lambda d: d["broker_onboarding"].update(required_human_items=["ok", ""]), "required_human_items"),
    (lambda d: d["broker_onboarding"].update(human_review_required="yes"), "must be true or false"),
    (lambda d: d["broker_onboarding"].update(recipe_name=""), "recipe_name"),
])
def test_malformed_recipes_are_refused_not_repaired(mutate, message):
    data = copy.deepcopy(SAMPLE)
    mutate(data)
    with pytest.raises(ValueError, match=message):
        parse_publisher_recipes(data)


def test_empty_recipe_file_is_refused():
    with pytest.raises(ValueError, match="non-empty"):
        parse_publisher_recipes({})


@pytest.mark.skipif(not REAL_RECIPES.is_file(), reason=f"{REAL_RECIPES} is not on this machine")
def test_real_publisher_recipes_file_loads():
    registry = load_recipe_registry(REAL_RECIPES)
    real = json.loads(REAL_RECIPES.read_text(encoding="utf-8"))
    loaded = [r for r in registry.all() if registry.detail(r.recipe_code) is not None]
    assert len(loaded) == len(real)
    for recipe in loaded:
        source = real[registry.detail(recipe.recipe_code).source_key]
        assert recipe.required_library_object_codes == source["required_company_items"]
        assert recipe.required_publisher_parts == source["required_publisher_items"]
