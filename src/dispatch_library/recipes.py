"""
Publisher Recipe Registry, held on the Library side per
DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md Section 4.2.

SCAFFOLD — PENDING REAL SOURCE: `publisher_recipes.json` was not found in any repo in scope
(see DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md Section 1). The five recipe *types* below are named
directly in DISPATCH_CONSTITUTION_v3.md Section 7.2/7.7 and PUBLISHER.md Sections 2/4 — they are
not invented. Their `required_library_object_codes` lists are placeholder scaffolding (empty or
minimal) pending the real recipe content. `resolve_packet()` never fabricates a resolution for a
missing object code; it reports MISSING explicitly.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from dispatch_library.models import PublisherRecipe, RecipeStatus, RecipeType
from dispatch_library.registry import ObjectRegistry
from dispatch_library.resolver import current as resolve_current

MISSING = "MISSING"


class RecipeRegistry:
    def __init__(self) -> None:
        self._recipes: Dict[str, PublisherRecipe] = {}

    def register(self, recipe: PublisherRecipe) -> PublisherRecipe:
        existing_current = self.get_current(recipe.recipe_type)
        if existing_current is not None:
            existing_current.status = RecipeStatus.SUPERSEDED
        self._recipes[recipe.recipe_code] = recipe
        return recipe

    def get_current(self, recipe_type: RecipeType) -> Optional[PublisherRecipe]:
        candidates = [
            r for r in self._recipes.values()
            if r.recipe_type == recipe_type and r.status == RecipeStatus.CURRENT
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.version)

    def all(self) -> List[PublisherRecipe]:
        return list(self._recipes.values())


def default_recipe_registry() -> RecipeRegistry:
    """Doctrine-named recipe types, scaffold content only (see module docstring)."""
    registry = RecipeRegistry()
    for recipe_type in (
        RecipeType.BROKER_ONBOARDING_PACKET,
        RecipeType.GOVERNMENT_PROPOSAL_PACKET,
        RecipeType.VISIBILITY_STATUS_PACKET,
        RecipeType.POD_PACKAGE,
        RecipeType.REVIEW_PACKAGE,
    ):
        registry.register(
            PublisherRecipe(
                recipe_code=f"RECIPE-{recipe_type.value}-v1",
                recipe_type=recipe_type,
                version=1,
                required_library_object_codes=[],
                required_publisher_parts=[],
                required_intelligence_requirement_types=[],
            )
        )
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
