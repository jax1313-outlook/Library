"""
Current Object Resolver — `library.current(object_code)`.

Returns only the CURRENT version of an object, or None. Superseded and draft-candidate versions
are never returned by this resolver, by construction (registry.add_version guarantees at most one
CURRENT version per object_code exists at any time).
"""
from __future__ import annotations

from typing import List, Optional

from dispatch_library.models import LibraryObject, LibraryObjectStatus
from dispatch_library.registry import ObjectRegistry


def current(registry: ObjectRegistry, object_code: str) -> Optional[LibraryObject]:
    for obj in registry.history(object_code):
        if obj.status == LibraryObjectStatus.CURRENT:
            return obj
    return None


def list_current(registry: ObjectRegistry, collection: Optional[str] = None) -> List[LibraryObject]:
    results = []
    for object_code in registry.all_object_codes():
        obj = current(registry, object_code)
        if obj is None:
            continue
        if collection is not None and obj.collection != collection:
            continue
        results.append(obj)
    return results
