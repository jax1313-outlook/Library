"""Opening the catalog, and refusing any file this Library must not write to.

One function matters here: `open_catalog()`. It returns a connection with the pragmas that make
SQLite safe for a program that may run beside the Portal, creates schema version 2 in a fresh
file, and refuses everything else.

What it refuses, and why:

  * **SQLite older than 3.31.** The schema uses a generated column and deferred foreign keys.
    On an older SQLite the script would fail halfway, or worse, run without the rule.
  * **A schema-version-1 file.** Version 1 was the superseded schema built by the S1-S5 work.
    It has no immutable ids, no approval records and no notices. Converting it would mean
    inventing the approval records it never kept, so it is refused, not migrated. No such file
    existed anywhere on D: when this was written.
  * **A file from a newer Library.** Opening it read-write could drop columns this code does
    not know it should keep.
  * **A non-empty file that is not a catalog.** Something else lives there.

Two pragma decisions worth reading before changing them:

  * `journal_mode = WAL` is issued once at open, with a retry, and not from `schema.sql`. It
    does not honour `busy_timeout`, so a lock at that moment would otherwise look like a corrupt
    schema.
  * `foreign_keys = ON` is per connection, not a property of the file, so it is set on every
    open. Without it the deferred approval-to-version key would never be checked.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

SCHEMA_VERSION = 2
MINIMUM_SQLITE = (3, 31, 0)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

#: SQLite's own default is five seconds, which is short for a laptop that is also writing
#: evidence files. A writer waits this long for another writer before giving up.
DEFAULT_TIMEOUT_SECONDS = 30.0

PathLike = Union[str, Path]


class CatalogError(RuntimeError):
    """The catalog could not be opened or brought to the current version."""


class CatalogVersionError(CatalogError):
    """The file holds a schema version this Library will not write to."""


class CatalogBusyError(CatalogError):
    """Another connection held the write lock for longer than the busy timeout."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sqlite_version() -> tuple:
    return tuple(int(part) for part in sqlite3.sqlite_version.split("."))


def require_supported_sqlite() -> None:
    if sqlite_version() < MINIMUM_SQLITE:
        raise CatalogError(
            f"SQLite {sqlite3.sqlite_version} is too old for the Library catalog; "
            f"{'.'.join(map(str, MINIMUM_SQLITE))} or later is required "
            "(generated columns and deferred foreign keys)."
        )


def _enable_wal(connection: sqlite3.Connection, attempts: int = 5) -> str:
    """Turn on WAL, retrying briefly if another connection holds the lock.

    Returns the journal mode actually in force. A filesystem that cannot do WAL still gets a
    working catalog, with less concurrency, and the caller can see which it got.
    """
    for attempt in range(attempts):
        try:
            return connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        except sqlite3.OperationalError:
            if attempt == attempts - 1:
                break
            time.sleep(0.1 * (attempt + 1))
    return connection.execute("PRAGMA journal_mode").fetchone()[0]


def connect(path: Optional[PathLike] = None, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> sqlite3.Connection:
    """A connection with the catalog's pragmas applied. No schema work.

    `isolation_level=None` puts transactions in this package's hands: every write path opens
    `BEGIN IMMEDIATE` itself, so the write lock is taken before the first read of a
    transaction, not upgraded halfway through it where SQLite cannot wait for it.
    """
    require_supported_sqlite()
    target = ":memory:" if path is None else str(path)
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=timeout, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    if path is not None:
        _enable_wal(connection)
    connection.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set:
    return {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def current_version(connection: sqlite3.Connection) -> int:
    """The schema version of an open catalog; 0 for an empty database."""
    tables = _tables(connection)
    if "schema_version" not in tables:
        return 0
    row = connection.execute("SELECT max(version) AS v FROM schema_version").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def migrate(connection: sqlite3.Connection) -> int:
    """Bring an open catalog to `SCHEMA_VERSION`, or refuse it. Returns the version in force."""
    tables = _tables(connection)
    version = current_version(connection)

    if version == SCHEMA_VERSION:
        return version
    if version > SCHEMA_VERSION:
        raise CatalogVersionError(
            f"catalog is at schema version {version}; this Library writes version {SCHEMA_VERSION}. "
            "Refusing to open it rather than risk dropping columns a newer version keeps."
        )
    if version == 1 or ("library_object" in tables and "library_version" not in tables):
        raise CatalogVersionError(
            "this is a schema-version-1 catalog from the superseded S1-S5 implementation. "
            "Version 2 keeps immutable ids, approval records and notices that version 1 never "
            "recorded, so it is not converted: converting would mean inventing those records. "
            "Move the file aside and open a new catalog."
        )
    if tables:
        raise CatalogError(
            f"the database holds tables ({', '.join(sorted(tables))}) but no Library schema "
            "version. It is not a Library catalog; refusing to write to it."
        )

    script = _SCHEMA_PATH.read_text(encoding="utf-8")
    try:
        connection.execute("BEGIN IMMEDIATE")
        # executescript() would COMMIT first; running the statements one by one keeps the whole
        # schema in this transaction, so a failure leaves an empty file rather than half a schema.
        for statement in _statements(script):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            (SCHEMA_VERSION, _now(), "Library catalog v2 (LIBRARY_IMPLEMENTATION_PLAN_v2)"),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    connection.execute("PRAGMA foreign_keys = ON")
    return SCHEMA_VERSION


def _statements(script: str):
    """Split the schema into complete statements, triggers included."""
    buffer = ""
    for line in script.splitlines(keepends=True):
        if line.lstrip().startswith("--") and not buffer.strip():
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement.upper().startswith("PRAGMA"):
                continue  # pragmas are set by connect(), outside the transaction
            yield statement
    if buffer.strip():
        raise CatalogError("schema.sql ends with an incomplete statement")


def open_catalog(path: Optional[PathLike] = None, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> sqlite3.Connection:
    """Open the catalog at `path`, creating schema version 2 in a new file, refusing any other.

    `path=None` opens an in-memory catalog: the full rules, nothing on disk, forgotten on close.
    """
    connection = connect(path, timeout=timeout)
    try:
        migrate(connection)
    except Exception:
        connection.close()
        raise
    return connection
