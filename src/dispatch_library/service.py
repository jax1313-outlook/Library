"""
Library service surfaces, per DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md Section 6:

    library.current(object_code)
    library.resolve_packet(recipe_type)
    library.submit_candidate(candidate)
    library.review_candidate(id, approve, reviewed_by)
    library.ingest_human_document(...)

`LibraryService` bundles an ObjectRegistry, CandidateQueue, and RecipeRegistry into one
integration point other repos (e.g. Publisher) can hold a reference to. Each method is a thin
wrapper over the corresponding module so the underlying logic stays independently testable.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from dispatch_library import ingestion, recipes as recipes_mod, resolver
from dispatch_library.models import LibraryCandidate, LibraryObject, PublisherRecipe, RecipeType
from dispatch_library.ingestion import CandidateQueue
from dispatch_library.registry import ObjectRegistry
from dispatch_library.recipes import RecipeRegistry


def _value(recipe_type) -> str:
    return getattr(recipe_type, "value", recipe_type)


class LibraryService:
    def __init__(
        self,
        registry: Optional[ObjectRegistry] = None,
        candidate_queue: Optional[CandidateQueue] = None,
        recipe_registry: Optional[RecipeRegistry] = None,
    ) -> None:
        self.registry = registry or ObjectRegistry()
        self.candidate_queue = candidate_queue or CandidateQueue()
        self.recipe_registry = recipe_registry or recipes_mod.default_recipe_registry()

    def current(self, object_code: str) -> Optional[LibraryObject]:
        return resolver.current(self.registry, object_code)

    def list_current(self, collection: Optional[str] = None) -> List[LibraryObject]:
        return resolver.list_current(self.registry, collection)

    def resolve_packet(self, recipe_type) -> Dict[str, object]:
        """Accepts a `RecipeType` or its string value -- Publisher's LibraryClient passes a string."""
        return recipes_mod.resolve_packet(self.registry, self.recipe_registry, RecipeType(_value(recipe_type)))

    def get_recipe(self, recipe_type) -> Optional[Dict[str, object]]:
        """`LibraryClient.get_recipe(recipe_type)`: the current recipe as a dict, or None.

        Publisher's protocol has always declared this method; LibraryService lacked it until plan
        v2. The dict carries `required_library_object_codes`, the key Publisher's StubLibraryClient
        reads, plus every field the recipe source supplied.
        """
        try:
            rtype = RecipeType(_value(recipe_type))
        except ValueError:
            return None
        recipe = self.recipe_registry.get_current(rtype)
        if recipe is None:
            return None
        detail = self.recipe_registry.detail(recipe.recipe_code)
        return {
            "recipe_code": recipe.recipe_code,
            "recipe_type": rtype.value,
            "version": recipe.version,
            "status": recipe.status.value,
            "is_placeholder": detail is None,
            "recipe_name": detail.recipe_name if detail else None,
            "source_key": detail.source_key if detail else None,
            "source_path": detail.source_path if detail else None,
            "human_review_required": detail.human_review_required if detail else None,
            "required_library_object_codes": list(recipe.required_library_object_codes),
            "required_publisher_parts": list(recipe.required_publisher_parts),
            "required_human_items": list(detail.required_human_items) if detail else [],
            "required_outputs": list(detail.required_outputs) if detail else [],
            "required_intelligence_requirement_types": list(recipe.required_intelligence_requirement_types),
        }

    def register_recipe(self, recipe: PublisherRecipe) -> PublisherRecipe:
        return self.recipe_registry.register(recipe)

    def ingest_human_document(
        self,
        object_code: str,
        collection: str,
        title: str,
        body_or_uri: str,
        accepted_by: str,
        tags: Optional[List[str]] = None,
    ) -> LibraryObject:
        return ingestion.ingest_human_document(
            self.registry, object_code, collection, title, body_or_uri, accepted_by, tags
        )

    def submit_candidate(self, candidate: LibraryCandidate) -> LibraryCandidate:
        return ingestion.submit_candidate(self.candidate_queue, candidate)

    def review_candidate(self, candidate_id: str, approve: bool, reviewed_by: str) -> LibraryCandidate:
        return ingestion.review_candidate(
            self.candidate_queue, self.registry, candidate_id, approve, reviewed_by
        )

    def pending_candidates(self) -> List[LibraryCandidate]:
        return self.candidate_queue.pending()
