"""Persistent catalog for the Library.

The database is the catalog; the shelf is the filesystem. Nothing in this
package moves, renames or rewrites an asset -- it records what exists, which
version is current, who accepted it, and what superseded it.

The rest of `dispatch_library` does not import this package. `LibraryService`
takes a registry and a queue by injection, so a caller chooses persistence and
nothing else has to know.
"""
from dispatch_library.catalog.connection import (
    CatalogError,
    CatalogVersionError,
    SCHEMA_VERSION,
    connect,
    current_version,
    migrate,
    open_catalog,
)

from dispatch_library.catalog.queue import SqliteCandidateQueue
from dispatch_library.catalog import shelf
from dispatch_library.catalog.registry import SqliteObjectRegistry
from dispatch_library.catalog.service import (
    CatalogLibraryService,
    library,
    open_library,
)

__all__ = [
    "CatalogLibraryService",
    "SqliteCandidateQueue",
    "SqliteObjectRegistry",
    "shelf",
    "library",
    "open_library",
    "CatalogError",
    "CatalogVersionError",
    "SCHEMA_VERSION",
    "connect",
    "current_version",
    "migrate",
    "open_catalog",
]
