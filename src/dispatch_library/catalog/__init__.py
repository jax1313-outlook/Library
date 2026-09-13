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

__all__ = [
    "CatalogError",
    "CatalogVersionError",
    "SCHEMA_VERSION",
    "connect",
    "current_version",
    "migrate",
    "open_catalog",
]
