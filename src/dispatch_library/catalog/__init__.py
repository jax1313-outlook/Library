"""The Library catalog: SQLite schema version 2, per LIBRARY_IMPLEMENTATION_PLAN_v2.

The database is the catalog; `DISPATCH_MEMORY_ROOT` is the shelf. Nothing in this package moves,
renames, writes or deletes a shelf file. It records what exists, which version is current, who
accepted it, what superseded it, what is waiting for a person, and what Library has noticed.

This package replaced the S1-S5 implementation of the superseded schema version 1. Those
commits remain in git history (c767856, a3cceb8, 5168a3f, aee174b); a version-1 file is refused.
"""
from dispatch_library.catalog.connection import (
    SCHEMA_VERSION,
    CatalogBusyError,
    CatalogError,
    CatalogVersionError,
    connect,
    current_version,
    migrate,
    open_catalog,
    sqlite_version,
)
from dispatch_library.catalog.queue import SqliteCandidateQueue
from dispatch_library.catalog.registry import SqliteObjectRegistry
from dispatch_library.catalog.service import (
    CATALOG_ENV,
    CatalogLibraryService,
    library,
    open_configured_library,
    open_library,
)
from dispatch_library.catalog.store import Catalog, CatalogRefusal, MissingObjectType, NotFound, ScanReport
from dispatch_library.catalog.pins import PinResult, PinService, open_pin_service

__all__ = [
    "PinResult", "PinService", "open_pin_service",
    "SCHEMA_VERSION", "CATALOG_ENV", "Catalog", "CatalogBusyError", "CatalogError", "CatalogLibraryService",
    "CatalogRefusal", "CatalogVersionError", "MissingObjectType", "NotFound", "ScanReport",
    "SqliteCandidateQueue", "SqliteObjectRegistry", "connect", "current_version", "library", "migrate",
    "open_catalog", "open_configured_library", "open_library", "sqlite_version",
]
