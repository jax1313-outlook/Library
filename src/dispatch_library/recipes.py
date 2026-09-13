"""
Publisher Recipe Registry, held on the Library side per
DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md Section 4.2.

SOURCE: `publisher_recipes.json`, kept by Mike at `D:\\Library\\publisher_recipes.json`. It is
read by `load_recipe_registry()`; nothing is copied into this repository, so the file on the
shelf stays the only copy.

That file defines TWO recipes: `broker_onboarding` and `government_proposal`. The other three
recipe *types* below are named in DISPATCH_CONSTITUTION_v3.md Section 7.2/7.7 and PUBLISHER.md
Sections 2/4, but have no real source yet. They remain SCAFFOLD with empty requirement lists, and
`RecipeRegistry.is_scaffold()` says so for each of them.

The JSON and `PublisherRecipe` do not have the same shape, and `PublisherRecipe` is field-locked
to the shared contract, so it is not changed here. The loader maps:

    required_company_items    -> PublisherRecipe.required_library_object_codes
    required_publisher_items  -> PublisherRecipe.required_publisher_parts
    required_human_items      -> RecipeSourceDetail.required_human_items
    required_outputs          -> RecipeSourceDetail.required_outputs
    human_review_required     -> RecipeSourceDetail.human_review_required

No field is dropped. The JSON has no intelligence requirements, so
`required_intelligence_requirement_types` stays empty for a loaded recipe; it is not invented.

The company items are item keys such as `w9`, not `LIB-COMPANY-W9-...` object codes. Until objects
are catalogued under those keys, `resolve_packet()` reports each of them MISSING — which is the
truth. `resolve_packet()` never fabricates a resolution for a missing object code.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Dict, List, Optional, Union

from dispatch_library.models import PublisherRecipe, RecipeStatus, RecipeType
from dispatch_library.registry import ObjectRegistry
from dispatch_library.resolver import current as resolve_current

MISSING = "MISSING"

# The JSON's own recipe_type names, matched to the doctrine-named RecipeType members. An entry
# whose type is not here is refused rather than guessed at.
_JSON_RECIPE_TYPES = {
    "broker_onboarding": RecipeType.BROKER_ONBOARDING_PACKET,
    "government_proposal": RecipeType.GOVERNMENT_PROPOSAL_PACKET,
}

_REQUIRED_LIST_FIELDS = (
    "required_company_items",
    "required_publisher_items",
    "required_human_items",
    "required_outputs",
)


@dataclasses.dataclass(frozen=True)
class RecipeSourceDetail:
    """The parts of a `publisher_recipes.json` entry that `PublisherRecipe` has no field for."""

    source_key: str
    recipe_name: str
    required_human_items: List[str]
    required_outputs: List[str]
    human_review_required: bool
    source_path: str


class RecipeRegistry:
    def __init__(self) -> None:
        self._recipes: Dict[str, PublisherRecipe] = {}
        self._details: Dict[str, RecipeSourceDetail] = {}

    def register(
        self, recipe: PublisherRecipe, detail: Optional[RecipeSourceDetail] = None
    ) -> PublisherRecipe:
        existing_current = self.get_current(recipe.recipe_type)
        if existing_current is not None:
            existing_current.status = RecipeStatus.SUPERSEDED
        self._recipes[recipe.recipe_code] = recipe
        if detail is not None:
            self._details[recipe.recipe_code] = detail
        return recipe

    def get_current(self, recipe_type: RecipeType) -> Optional[PublisherRecipe]:
        candidates = [
            r for r in self._recipes.values()
            if r.recipe_type == recipe_type and r.status == RecipeStatus.CURRENT
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.version)

    def detail(self, recipe_code: str) -> Optional[RecipeSourceDetail]:
        return self._details.get(recipe_code)

    def is_scaffold(self, recipe_type: RecipeType) -> bool:
        """True when the current recipe of this type has no real source behind it."""
        recipe = self.get_current(recipe_type)
        return recipe is None or recipe.recipe_code not in self._details

    def all(self) -> List[PublisherRecipe]:
        return list(self._recipes.values())


_DOCTRINE_RECIPE_TYPES = (
    RecipeType.BROKER_ONBOARDING_PACKET,
    RecipeType.GOVERNMENT_PROPOSAL_PACKET,
    RecipeType.VISIBILITY_STATUS_PACKET,
    RecipeType.POD_PACKAGE,
    RecipeType.REVIEW_PACKAGE,
)


def _scaffold_recipe(recipe_type: RecipeType) -> PublisherRecipe:
    return PublisherRecipe(
        recipe_code=f"RECIPE-{recipe_type.value}-v1",
        recipe_type=recipe_type,
        version=1,
        required_library_object_codes=[],
        required_publisher_parts=[],
        required_intelligence_requirement_types=[],
    )


def default_recipe_registry() -> RecipeRegistry:
    """Doctrine-named recipe types, scaffold content only (see module docstring)."""
    registry = RecipeRegistry()
    for recipe_type in _DOCTRINE_RECIPE_TYPES:
        registry.register(_scaffold_recipe(recipe_type))
    return registry


def _string_list(entry: Dict[str, object], field: str, key: str) -> List[str]:
    value = entry.get(field)
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"recipe {key!r}: {field} must be a list of non-empty strings")
    return list(value)


def parse_publisher_recipes(
    data: object, source_path: str = "<memory>"
) -> List[tuple]:
    """Validate parsed `publisher_recipes.json` content into (PublisherRecipe, detail) pairs.

    Refuses rather than repairs: an unknown recipe type, a key that disagrees with its own
    recipe_type, a missing list, or a non-boolean human_review_required all raise ValueError.
    """
    if not isinstance(data, dict) or not data:
        raise ValueError("publisher_recipes.json must be a non-empty object of recipes")

    loaded = []
    seen_types = set()
    for key, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"recipe {key!r} must be an object")
        json_type = entry.get("recipe_type")
        if json_type != key:
            raise ValueError(f"recipe {key!r}: recipe_type {json_type!r} does not match its key")
        if json_type not in _JSON_RECIPE_TYPES:
            raise ValueError(
                f"recipe {key!r}: recipe_type {json_type!r} matches no doctrine recipe type "
                f"(known: {sorted(_JSON_RECIPE_TYPES)})"
            )
        recipe_type = _JSON_RECIPE_TYPES[json_type]
        if recipe_type in seen_types:
            raise ValueError(f"recipe {key!r}: a second recipe for {recipe_type.value}")
        seen_types.add(recipe_type)

        recipe_name = entry.get("recipe_name")
        if not isinstance(recipe_name, str) or not recipe_name:
            raise ValueError(f"recipe {key!r}: recipe_name must be a non-empty string")
        lists = {field: _string_list(entry, field, key) for field in _REQUIRED_LIST_FIELDS}
        review = entry.get("human_review_required")
        if not isinstance(review, bool):
            raise ValueError(f"recipe {key!r}: human_review_required must be true or false")

        recipe = PublisherRecipe(
            recipe_code=f"RECIPE-{recipe_type.value}-v1",
            recipe_type=recipe_type,
            version=1,
            required_library_object_codes=lists["required_company_items"],
            required_publisher_parts=lists["required_publisher_items"],
            required_intelligence_requirement_types=[],
        )
        detail = RecipeSourceDetail(
            source_key=key,
            recipe_name=recipe_name,
            required_human_items=lists["required_human_items"],
            required_outputs=lists["required_outputs"],
            human_review_required=review,
            source_path=source_path,
        )
        loaded.append((recipe, detail))
    return loaded


def load_recipe_registry(path: Union[str, Path]) -> RecipeRegistry:
    """A registry holding every recipe in `publisher_recipes.json`, plus scaffold for the rest.

    A type the file defines is registered from the file only; no scaffold version of it is
    created, so there is no superseded placeholder pretending to be history.
    """
    path = Path(path)
    loaded = parse_publisher_recipes(json.loads(path.read_text(encoding="utf-8")), str(path))

    registry = RecipeRegistry()
    for recipe, detail in loaded:
        registry.register(recipe, detail)
    for recipe_type in _DOCTRINE_RECIPE_TYPES:
        if registry.get_current(recipe_type) is None:
            registry.register(_scaffold_recipe(recipe_type))
    return registry


def resolve_packet(
    registry: ObjectRegistry,
    recipe_registry: RecipeRegistry,
    recipe_type: RecipeType,
) -> Dict[str, object]:
    """`library.resolve_packet(recipe_type)` — resolve a recipe's required Library objects.

    Returns {object_code: LibraryObject | "MISSING"}. Never invents a substitute for a missing
    object code (No Fabrication Rule).
    """
    recipe = recipe_registry.get_current(recipe_type)
    if recipe is None:
        return {}

    resolved: Dict[str, object] = {}
    for object_code in recipe.required_library_object_codes:
        obj = resolve_current(registry, object_code)
        resolved[object_code] = obj if obj is not None else MISSING
    return resolved
