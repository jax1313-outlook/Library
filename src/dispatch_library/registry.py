"""
Library Object Registry — versioned storage for LibraryObject records.

Supersession is automatic and structural: adding a new CURRENT version of an object_code
immediately flips the previous CURRENT version of that object_code to SUPERSEDED. There is no
code path that leaves two CURRENT versions of the same object_code at once, which is what the
`current()` resolver's correctness depends on.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from dispatch_library.models import LibraryObject, LibraryObjectStatus


class ObjectRegistry:
    def __init__(self) -> None:
        # object_code -> list of LibraryObject, ordered by version ascending
        self._versions: Dict[str, List[LibraryObject]] = {}

    def add_version(self, obj: LibraryObject) -> LibraryObject:
        history = self._versions.setdefault(obj.object_code, [])

        if obj.status == LibraryObjectStatus.CURRENT:
            for existing in history:
                if existing.status == LibraryObjectStatus.CURRENT:
                    existing.status = LibraryObjectStatus.SUPERSEDED

        history.append(obj)
        history.sort(key=lambda o: o.version)
        return obj

    def next_version(self, object_code: str) -> int:
        history = self._versions.get(object_code, [])
        if not history:
            return 1
        return max(o.version for o in history) + 1

    def history(self, object_code: str) -> List[LibraryObject]:
        return list(self._versions.get(object_code, []))

    def all_object_codes(self) -> List[str]:
        return list(self._versions.keys())

    def get_version(self, object_code: str, version: int) -> Optional[LibraryObject]:
        for obj in self._versions.get(object_code, []):
            if obj.version == version:
                return obj
        return None
