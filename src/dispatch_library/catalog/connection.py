"""Opening the catalog, and bringing it up to the current schema version.

One function matters here: `open_catalog()`. It returns a connection with the
pragmas that make SQLite safe for a program that may be running beside the
Portal, and it applies any migration the file has not seen.

Two pragma decisions are worth reading before changing them:

  * `journal_mode = WAL` is issued **before** anything else, and deliberately
    not from `schema.sql`. It does not honour `busy_timeout` -- it takes an
    exclusive lock and fails immediately if another connection holds one -- so
    it is issued once, at open, with a retry around it rather than buried in a
    script where a lock failure would look like a corrupt schema.

  * `foreign_keys = ON` is per-connection in SQLite, not a property of the
    file. Setting it in `schema.sql` alone would enforce it exactly once, on
    the connection that created the database, and never again.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

#: SQLite's own default is five seconds, which is short for a laptop writing
#: evidence files at the same time.
DEFAULT_TIMEOUT_SECONDS = 30.0


class CatalogError(RuntimeError):
    """The catalog could not be opened or brought to the current version."""


class CatalogVersionError(CatalogError):
    """The file was written by a newer Library than this one.

    Refusing is the point. A newer schema may carry columns this code does not
    write, and opening it read-write would quietly drop them.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enable_wal(connection: sqlite3.Connection, attempts: int = 5) -> None:
    """Turn on WAL, retrying briefly if another connection holds the lock.

    Failure is not fatal. An in-memory database cannot use WAL at all, and a
    catalog on a filesystem that does not support it still works -- just with
    less concurrency. Refusing to open the catalog over a journal-mode
    preference would be a worse outcome than the preference not being met.
    """
    for attempt in range(attempts):
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError:
            if attempt == attempts - 1:
                return
            time.sleep(0.1 * (attempt + 1))


def connect(path: Optional[Path | str] = None, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> sqlite3.Connection:
    """A connection with the catalog's pragmas applied. No schema work."""
    target = ":memory:" if path is None else str(path)
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(target, timeout=timeout)
    connection.row_factory = sqlite3.Row
    if path is not None:
        _enable_wal(connection)
    connection.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def current_version(connection: sqlite3.Connection) -> int:
    """The schema version of an open catalog; 0 for an empty database."""
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if row is None:
        return 0
    row = connection.execute("SELECT max(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def migrate(connection: sqlite3.Connection) -> int:
    """Bring an open catalog to `SCHEMA_VERSION`. Returns the version applied.

    Idempotent: running it against a current catalog does nothing and returns
    the version it already had.
    """
    version = current_version(connection)

    if version > SCHEMA_VERSION:
        raise CatalogVersionError(
            f"catalog is at schema version {version}; this Library understands "
            f"{SCHEMA_VERSION}. Refusing to open it rather than risk dropping "
            f"columns a newer version writes."
        )
    if version == SCHEMA_VERSION:
        return version

    if version == 0:
        # The whole script runs inside one transaction. A schema left half
        # created is worse than no schema at all, because the next open would
        # read a version of 0 and try to create the tables that already exist.
        with connection:
            connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _now()),
            )
        # executescript() commits any open transaction before it runs, which
        # clears the PRAGMA set at connect time on some builds. Re-assert it.
        connection.execute("PRAGMA foreign_keys = ON")
        return SCHEMA_VERSION

    # No migration from 1 exists yet. When one does, it goes here as an
    # explicit step -- never as a blind re-run of schema.sql over live data.
    raise CatalogError(  # pragma: no cover - unreachable while SCHEMA_VERSION == 1
        f"no migration path from schema version {version} to {SCHEMA_VERSION}"
    )


def open_catalog(
    path: Optional[Path | str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> sqlite3.Connection:
    """Open the catalog at `path`, creating or migrating it as needed.

    `path=None` opens an in-memory catalog, which is what the tests use and
    what makes the registry runnable with no file on disk.
    """
    connection = connect(path, timeout=timeout)
    try:
        migrate(connection)
    except Exception:
        connection.close()
        raise
    return connection
