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

    def resolve_packet(self, recipe_type: RecipeType) -> Dict[str, object]:
        return recipes_mod.resolve_packet(self.registry, self.recipe_registry, recipe_type)

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
