"""Opening a catalog: what is created, and what is refused."""
from __future__ import annotations

import sqlite3

import pytest

from dispatch_library.catalog import (
    SCHEMA_VERSION,
    CatalogError,
    CatalogVersionError,
    current_version,
    open_catalog,
    sqlite_version,
)
from dispatch_library.catalog.connection import MINIMUM_SQLITE


def test_this_sqlite_is_supported():
    assert sqlite_version() >= MINIMUM_SQLITE


def test_a_new_file_gets_the_current_schema_version_in_wal_mode(tmp_path):
    path = tmp_path / "catalog.db"
    connection = open_catalog(path)
    assert current_version(connection) == SCHEMA_VERSION == 3
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM library_collection").fetchone()[0] == 15
    connection.close()
    assert path.is_file()


def test_reopening_is_idempotent(tmp_path):
    path = tmp_path / "catalog.db"
    open_catalog(path).close()
    connection = open_catalog(path)
    assert connection.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 2  # versions 2 and 3
    assert connection.execute("SELECT count(*) FROM library_collection").fetchone()[0] == 15
    connection.close()


def test_foreign_keys_are_on_for_every_connection(tmp_path):
    path = tmp_path / "catalog.db"
    open_catalog(path).close()
    connection = open_catalog(path)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()


def _make_v1_file(path):
    """The shape S1-S5 wrote: library_object keyed by (object_code, version), schema_version 1."""
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE library_object (object_code TEXT, version INTEGER, PRIMARY KEY (object_code, version));"
        "CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL);"
        "INSERT INTO schema_version VALUES (1, '2026-09-13T18:31:12Z');"
    )
    db.commit()
    db.close()


def test_a_schema_version_one_file_is_refused_not_converted(tmp_path):
    path = tmp_path / "old.db"
    _make_v1_file(path)
    with pytest.raises(CatalogVersionError, match="schema-version-1"):
        open_catalog(path)
    db = sqlite3.connect(path)
    assert [r[0] for r in db.execute("SELECT version FROM schema_version")] == [1]
    assert db.execute("SELECT count(*) FROM sqlite_master WHERE name = 'library_version'").fetchone()[0] == 0
    db.close()


def test_a_version_one_shape_without_its_version_row_is_still_refused(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE library_object (object_code TEXT, version INTEGER)")
    db.commit()
    db.close()
    with pytest.raises(CatalogVersionError):
        open_catalog(path)


def test_a_newer_schema_is_refused(tmp_path):
    path = tmp_path / "new.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT, description TEXT)")
    db.execute("INSERT INTO schema_version VALUES (4, 'later', 'future')")
    db.commit()
    db.close()
    with pytest.raises(CatalogVersionError, match="version 4"):
        open_catalog(path)


def test_a_database_that_is_not_a_catalog_is_refused(tmp_path):
    path = tmp_path / "dispatch.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE loads (load_id TEXT)")
    db.commit()
    db.close()
    with pytest.raises(CatalogError, match="not a Library catalog"):
        open_catalog(path)


def test_in_memory_catalog_has_every_rule(tmp_path):
    connection = open_catalog(None)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO library_collection (collection_id, name) VALUES ('Fuel', 'Fuel')")
    connection.close()
