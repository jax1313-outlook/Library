"""`Catalog` -- every Library write and read against schema version 2.

The schema holds the rules; this module does the work in the order the rules require, and
turns a database refusal into an error a person can read. It never adds a rule the schema does
not have, and it never relaxes one: if Python and SQLite ever disagree, SQLite wins, because it
is the one a careless future caller cannot skip.

Every write is one `BEGIN IMMEDIATE` transaction. `IMMEDIATE` takes the write lock before the
first read, so two writers superseding the same object queue behind each other instead of both
reading "v1 is current" and one of them failing halfway.

What this module will not do, by design:

  * **Move, rename, write or delete a file on the shelf.** It opens shelf files to hash them.
  * **Adopt a file.** A scan reports an uncatalogued file; only `place()` with a human name
    turns one into a Library object.
  * **Infer an object type.** Collection is where an asset belongs; type is what it is. A
    missing type is refused and becomes a MISSING_FIELD notice (plan v2 ruling 3).
  * **Nominate.** Library classifies, validates, detects and notifies. Candidates arrive from a
    human, Intelligence, Publisher or a Dispatch workflow (ruling 5).
  * **Approve.** Nine system identities are refused as approvers (ruling 6). A capture channel
    such as JOE is recorded beside the human approver, never instead of one.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from dispatch_library.catalog.connection import CatalogBusyError
from dispatch_library.models import (
    CURRENT_STATES,
    OBJECT_TYPES,
    LifecycleState,
    is_reserved_identity,
    normalize_identity,
)
from dispatch_library.taxonomy import require_valid_collection

#: Current plus this many previous versions are retained without review
#: (ARCHIVE_REVIEW_POLICY.md sections 2-4).
RETAINED_PREVIOUS_VERSIONS = 3

CANDIDATE_SOURCES = ("HUMAN", "INTELLIGENCE", "PUBLISHER", "DISPATCH")
#: May not settle a notice: Library itself and the systems that are never an authorised source.
NOTICE_RESOLVER_REFUSED = ("LIBRARY", "JOE", "SYSTEM", "AUTOMATION", "COMI", "EMAIL_HELPER")

_READ_CHUNK = 1024 * 1024

IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep", ".gitignore"})
IGNORED_DIRECTORIES = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".svn", "$RECYCLE.BIN", "System Volume Information",
})
IGNORED_SUFFIXES = frozenset({".tmp", ".swp", ".pyc", ".lock"})


class CatalogRefusal(ValueError):
    """The catalog refused a write. A ValueError, so existing callers keep catching it."""


class MissingObjectType(CatalogRefusal):
    """Acceptance refused because no object type was given. Carries the notice it raised."""

    def __init__(self, message: str, notice_id: Optional[str]) -> None:
        super().__init__(message)
        self.notice_id = notice_id


class NotFound(KeyError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def is_ignorable(relative: PurePosixPath) -> bool:
    if relative.name in IGNORED_NAMES or relative.suffix.lower() in IGNORED_SUFFIXES:
        return True
    return any(part in IGNORED_DIRECTORIES for part in relative.parts)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "object"


def normalise_relative_path(relative_path: str) -> str:
    """POSIX separators, no leading slash, no escape from the shelf."""
    text = str(relative_path).replace("\\", "/").strip()
    posix = PurePosixPath(text)
    if posix.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in posix.parts or not text:
        raise CatalogRefusal(f"{relative_path!r} is not a path inside the shelf")
    return posix.as_posix()


@dataclass
class ScanReport:
    scan_id: Optional[int]
    memory_root: str
    files_seen: int = 0
    folders_seen: int = 0
    catalogued: int = 0
    findings: List[Tuple[str, str, str]] = field(default_factory=list)  # (finding, path, detail)

    def of(self, kind: str) -> List[Tuple[str, str, str]]:
        return [f for f in self.findings if f[0] == kind]

    def counts(self) -> Dict[str, int]:
        kinds = ("UNCATALOGUED", "CHANGED", "MISSING", "UNMAPPED_FOLDER", "PLACEMENT_CONFLICT")
        return {k: len(self.of(k)) for k in kinds}


class Catalog:
    """The catalog over one connection. Holds the connection; the caller owns and closes it."""

    def __init__(self, connection: sqlite3.Connection, *, memory_root: Optional[Path] = None) -> None:
        self.db = connection
        self.memory_root = Path(memory_root) if memory_root else None

    # ── transactions ─────────────────────────────────────────────────────

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """One `BEGIN IMMEDIATE` transaction, with refusals made readable."""
        try:
            self.db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) or "busy" in str(exc):
                raise CatalogBusyError(
                    "another connection held the catalog's write lock past the busy timeout"
                ) from exc
            raise
        try:
            yield self.db
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self._rollback()
            raise CatalogRefusal(f"the catalog refused the write: {exc}") from exc
        except sqlite3.OperationalError as exc:
            self._rollback()
            if "locked" in str(exc) or "busy" in str(exc):
                raise CatalogBusyError(str(exc)) from exc
            raise
        except BaseException:
            self._rollback()
            raise

    def _rollback(self) -> None:
        if self.db.in_transaction:
            self.db.execute("ROLLBACK")

    def _one(self, sql: str, params: Sequence = ()) -> Optional[sqlite3.Row]:
        return self.db.execute(sql, params).fetchone()

    def _all(self, sql: str, params: Sequence = ()) -> List[sqlite3.Row]:
        return self.db.execute(sql, params).fetchall()

    # ── identities ───────────────────────────────────────────────────────

    @staticmethod
    def require_human(name: Optional[str], role: str) -> str:
        if not name or not name.strip():
            raise CatalogRefusal(f"{role} must name a real person")
        if is_reserved_identity(name):
            raise CatalogRefusal(
                f"{role} {name!r} is a system identity. No system identity may stand as a human "
                "approval; record a channel such as JOE as capture_channel beside the person."
            )
        return name.strip()

    # ── objects and versions ─────────────────────────────────────────────

    def object_row(self, object_code: str) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM library_object WHERE object_code = ?", (object_code,))

    def current_row(self, object_code: str) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM library_current WHERE object_code = ?", (object_code,))

    def version_rows(self, object_code: str) -> List[sqlite3.Row]:
        return self._all(
            "SELECT v.*, a.approver, a.approved_at, a.approval_basis, a.capture_channel, "
            "l.superseded_by_version_id, o.object_code, o.object_type, o.collection_id "
            "FROM library_version v JOIN library_object o USING (library_object_id) "
            "JOIN approval_record a ON a.approval_record_id = v.approval_record_id "
            "JOIN library_version_lineage l ON l.version_id = v.version_id "
            "WHERE o.object_code = ? ORDER BY v.version_major, v.version_minor",
            (object_code,),
        )

    def version_row(self, version_id: str) -> Optional[sqlite3.Row]:
        return self._one(
            "SELECT v.*, a.approver, a.approved_at, a.approval_basis, a.capture_channel, "
            "o.object_code, o.object_type, o.collection_id "
            "FROM library_version v JOIN library_object o USING (library_object_id) "
            "JOIN approval_record a ON a.approval_record_id = v.approval_record_id "
            "WHERE v.version_id = ?",
            (version_id,),
        )

    def all_object_codes(self) -> List[str]:
        return [r[0] for r in self._all("SELECT object_code FROM library_object ORDER BY object_code")]

    def list_current(self, collection: Optional[str] = None) -> List[sqlite3.Row]:
        if collection:
            return self._all("SELECT * FROM library_current WHERE collection_id = ? ORDER BY object_code", (collection,))
        return self._all("SELECT * FROM library_current ORDER BY object_code")

    def _next_version(self, library_object_id: Optional[str], minor: bool) -> Tuple[int, int]:
        if library_object_id is None:
            return 1, 0
        row = self._one(
            "SELECT version_major, version_minor FROM library_version WHERE library_object_id = ? "
            "ORDER BY version_major DESC, version_minor DESC LIMIT 1",
            (library_object_id,),
        )
        if row is None:
            return 1, 0
        if minor:
            return row["version_major"], row["version_minor"] + 1
        return row["version_major"] + 1, 0

    def _shelf_facts(self, relative_path: str) -> Tuple[str, str, int]:
        if self.memory_root is None:
            raise CatalogRefusal("this catalog is not bound to a shelf; open it with a memory_root")
        rel = normalise_relative_path(relative_path)
        path = self.memory_root / rel
        if not path.is_file():
            raise CatalogRefusal(f"no file at {rel!r} under {self.memory_root}")
        return rel, sha256_of(path), path.stat().st_size

    def _missing_type_notice(self, subject_path: str, object_code: str, recommended: Optional[str]) -> str:
        return self.raise_notice(
            "MISSING_FIELD",
            relative_path=subject_path,
            missing_field="object_type",
            recommended_object_type=recommended,
            recommended_action=(
                "Confirm what this asset is. Collection says where it belongs; object type says "
                "what it is, and Library does not infer one from the other."
            ),
            detail=f"Acceptance of {object_code} refused: no object_type was given.",
        )

    def place(
        self,
        *,
        object_code: str,
        collection: str,
        title: str,
        accepted_by: str,
        object_type: Optional[str] = None,
        body: Optional[str] = None,
        relative_path: Optional[str] = None,
        slug: Optional[str] = None,
        canonical_name: Optional[str] = None,
        tags: Iterable[str] = (),
        minor: bool = False,
        version: Optional[Tuple[int, int]] = None,
        capture_channel: Optional[str] = None,
        capture_ref: Optional[str] = None,
        authority_basis: Optional[str] = None,
        effective_date: Optional[str] = None,
        review_due_date: Optional[str] = None,
        recommended_object_type: Optional[str] = None,
    ) -> sqlite3.Row:
        """A human places and accepts a document: direct acceptance, no second gate (ruling 4).

        Writes the object (first placement), the approval record, and the version in one
        transaction, superseding the current version if there is one. Refuses a system
        identity, a missing object type (and records a MISSING_FIELD notice), a change of type or
        collection for an existing object, and content that is neither inline nor on the shelf.
        """
        require_valid_collection(collection)
        approver = self.require_human(accepted_by, "accepted_by")
        if (body is None) == (relative_path is None):
            raise CatalogRefusal("a placement carries exactly one of an inline body or a shelf path")

        existing = self.object_row(object_code)
        if object_type is None and existing is not None:
            object_type = existing["object_type"]
        if object_type is None:
            subject = normalise_relative_path(relative_path) if relative_path else f"(inline) {object_code}"
            notice_id = self._missing_type_notice(subject, object_code, recommended_object_type)
            raise MissingObjectType(
                f"acceptance of {object_code!r} refused: object_type is required and is never inferred "
                f"from collection. Notice {notice_id} records it.",
                notice_id,
            )
        if object_type not in OBJECT_TYPES:
            raise CatalogRefusal(f"object_type {object_type!r} is not one of the Core Object Model types")
        if existing is not None and existing["object_type"] != object_type:
            raise CatalogRefusal(
                f"{object_code} is a {existing['object_type']}; a different type is a different object"
            )
        if existing is not None and existing["collection_id"] != collection:
            raise CatalogRefusal(
                f"{object_code} belongs to {existing['collection_id']}; moving collection is a new object"
            )

        rel = sha = size = None
        if relative_path is not None:
            rel, sha, size = self._shelf_facts(relative_path)
        content_uri = f"shelf:{rel}" if rel else f"inline:{object_code}"
        now = _now()

        with self.write() as db:
            # Read again under the write lock: another process may have placed this object between
            # the checks above and BEGIN IMMEDIATE. Without this, two first placements race and one
            # fails on the unique object code instead of becoming version 2.
            existing = self.object_row(object_code)
            if existing is not None and (existing["object_type"] != object_type or existing["collection_id"] != collection):
                raise CatalogRefusal(
                    f"{object_code} is a {existing['object_type']} in {existing['collection_id']}; "
                    "a different type or collection is a different object"
                )
            if existing is None:
                library_object_id = _id("libobj_")
                db.execute(
                    "INSERT INTO library_object (library_object_id, object_code, object_type, collection_id, "
                    "title, slug, canonical_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (library_object_id, object_code, object_type, collection, title,
                     slug or _slug(object_code), canonical_name or title, now, now),
                )
            else:
                library_object_id = existing["library_object_id"]
                db.execute(
                    "UPDATE library_object SET title = ?, updated_at = ? WHERE library_object_id = ?",
                    (title, now, library_object_id),
                )
            major, minor_n = version or self._next_version(library_object_id if existing else None, minor)
            supersedes = self._flip_current(library_object_id)
            version_id = _id("libver_")
            approval_id = _id("apr_")
            db.execute(
                "INSERT INTO approval_record (approval_record_id, library_object_id, version_id, approver, "
                "approval_status, approval_basis, authority_basis, capture_channel, capture_ref, approved_at) "
                "VALUES (?,?,?,?, 'APPROVED', 'HUMAN_PLACED', ?,?,?,?)",
                (approval_id, library_object_id, version_id, approver, authority_basis,
                 capture_channel, capture_ref, now),
            )
            db.execute(
                "INSERT INTO library_version (version_id, library_object_id, version_major, version_minor, "
                "lifecycle_state, title, content_uri, body, relative_path, content_sha256, size_bytes, "
                "observed_at, effective_date, review_due_date, supersedes_version_id, approval_record_id, "
                "created_at) VALUES (?,?,?,?, 'CURRENT', ?,?,?,?,?,?,?,?,?,?,?,?)",
                (version_id, library_object_id, major, minor_n, title, content_uri, body, rel, sha, size,
                 now if rel else None, effective_date, review_due_date, supersedes, approval_id, now),
            )
            for position, tag in enumerate(dict.fromkeys(tags)):
                db.execute(
                    "INSERT OR IGNORE INTO library_object_tag (library_object_id, tag, position) VALUES (?,?,?)",
                    (library_object_id, tag, position),
                )
            if rel:
                db.execute(
                    "INSERT INTO source_ref (source_ref_id, version_id, ref_kind, reference) VALUES (?,?, 'SHELF_FILE', ?)",
                    (_id("src_"), version_id, rel),
                )
            self._queue_retention(library_object_id, now)
        return self.version_row(version_id)

    def _flip_current(self, library_object_id: str) -> Optional[str]:
        row = self._one(
            "SELECT version_id FROM library_version WHERE library_object_id = ? AND is_current = 1",
            (library_object_id,),
        )
        if row is None:
            prior = self._one(
                "SELECT version_id FROM library_version WHERE library_object_id = ? AND lifecycle_state = 'SUPERSEDED' "
                "AND version_id NOT IN (SELECT supersedes_version_id FROM library_version WHERE supersedes_version_id IS NOT NULL) "
                "ORDER BY version_major DESC, version_minor DESC LIMIT 1",
                (library_object_id,),
            )
            return prior["version_id"] if prior else None
        self.db.execute(
            "UPDATE library_version SET lifecycle_state = 'SUPERSEDED' WHERE version_id = ?", (row["version_id"],)
        )
        return row["version_id"]

    def _queue_retention(self, library_object_id: str, now: str) -> None:
        """Current plus three previous are kept; older versions queue for a human decision."""
        rows = self._all(
            "SELECT version_id, is_current FROM library_version WHERE library_object_id = ? "
            "ORDER BY version_major DESC, version_minor DESC",
            (library_object_id,),
        )
        for row in rows[1 + RETAINED_PREVIOUS_VERSIONS:]:
            if row["is_current"]:
                continue
            self.db.execute(
                "INSERT OR IGNORE INTO archive_review_queue (version_id, queued_at) VALUES (?, ?)",
                (row["version_id"], now),
            )

    def set_lifecycle(self, object_code: str, state: str, *, by: Optional[str] = None) -> sqlite3.Row:
        """Move the current version among CURRENT, ACTIVE_USE and REVIEW_DUE.

        Marking REVIEW_DUE is Library's detection and needs no name; it raises an EXPIRED notice.
        Leaving REVIEW_DUE is a renewal -- a person saying the asset may be used again -- so it
        needs that person's name, and their renewal closes the EXPIRED notice in their name.
        """
        if state not in {s.value for s in CURRENT_STATES}:
            raise CatalogRefusal(f"{state!r} is not a current lifecycle state; supersede or archive instead")
        current = self.current_row(object_code)
        if current is None:
            raise NotFound(object_code)
        renewing = current["lifecycle_state"] == LifecycleState.REVIEW_DUE.value and state != LifecycleState.REVIEW_DUE.value
        person = self.require_human(by, "a renewal") if renewing else None
        with self.write() as db:
            db.execute("UPDATE library_version SET lifecycle_state = ? WHERE version_id = ?",
                       (state, current["current_version_id"]))
            if state == LifecycleState.REVIEW_DUE.value:
                self._raise_notice_in_txn(
                    "EXPIRED", version_id=current["current_version_id"],
                    recommended_action="Renew or replace before any external use.",
                    detail=f"{object_code} is due for review and is blocked from external use.",
                )
            if renewing:
                db.execute(
                    "UPDATE library_notice SET status = 'RESOLVED', resolved_by = ?, resolved_at = ?, resolution = ? "
                    "WHERE version_id = ? AND notice_type = 'EXPIRED' AND status = 'OPEN'",
                    (person, _now(), f"renewed by {person}; returned to {state}", current["current_version_id"]),
                )
        return self.current_row(object_code)

    def mark_review_due(self, today: Optional[str] = None) -> List[str]:
        """Every current version whose review_due_date has passed becomes REVIEW_DUE."""
        today = today or datetime.now(timezone.utc).date().isoformat()
        rows = self._all(
            "SELECT o.object_code FROM library_version v JOIN library_object o USING (library_object_id) "
            "WHERE v.lifecycle_state IN ('CURRENT','ACTIVE_USE') AND v.review_due_date IS NOT NULL "
            "AND v.review_due_date < ?",
            (today,),
        )
        codes = [r["object_code"] for r in rows]
        for code in codes:
            self.set_lifecycle(code, LifecycleState.REVIEW_DUE.value)
        return codes

    def archive_version(self, version_id: str, archive_record_id: str, description: str = "") -> sqlite3.Row:
        row = self.version_row(version_id)
        if row is None:
            raise NotFound(version_id)
        with self.write() as db:
            db.execute(
                "INSERT INTO archive_link (archive_link_id, library_object_id, version_id, archive_record_id, "
                "relationship_type, description, created_at) VALUES (?,?,?,?, 'SUPERSEDED_VERSION', ?, ?)",
                (_id("arl_"), row["library_object_id"], version_id, archive_record_id, description, _now()),
            )
            db.execute("UPDATE library_version SET lifecycle_state = 'ARCHIVED_VERSION_RECORD' WHERE version_id = ?",
                       (version_id,))
        return self.version_row(version_id)

    def retention_queue(self, disposition: Optional[str] = "PENDING") -> List[sqlite3.Row]:
        sql = ("SELECT q.*, o.object_code, v.version_major, v.version_minor, v.lifecycle_state "
               "FROM archive_review_queue q JOIN library_version v USING (version_id) "
               "JOIN library_object o USING (library_object_id)")
        if disposition:
            return self._all(sql + " WHERE q.disposition = ? ORDER BY q.queued_at", (disposition,))
        return self._all(sql + " ORDER BY q.queued_at")

    def decide_retention(self, version_id: str, disposition: str, decided_by: str) -> sqlite3.Row:
        """Record Mike's Keep/Delete decision. A DELETE is recorded; nothing is deleted here."""
        person = self.require_human(decided_by, "decided_by")
        row = self.version_row(version_id)
        if row is None:
            raise NotFound(version_id)
        with self.write() as db:
            if row["lifecycle_state"] == "ARCHIVED_VERSION_RECORD":
                db.execute("UPDATE library_version SET lifecycle_state = 'RETENTION_REVIEW' WHERE version_id = ?",
                           (version_id,))
            db.execute(
                "UPDATE archive_review_queue SET disposition = ?, decided_by = ?, decided_at = ? WHERE version_id = ?",
                (disposition, person, _now(), version_id),
            )
        return self._one("SELECT * FROM archive_review_queue WHERE version_id = ?", (version_id,))

    # ── metadata, sources, relationships ─────────────────────────────────

    def set_metadata(self, object_code: str, key: str, value: str, value_type: str = "TEXT",
                     *, version_bound: bool = False) -> None:
        current = self.current_row(object_code)
        obj = self.object_row(object_code)
        if obj is None:
            raise NotFound(object_code)
        version_id = current["current_version_id"] if (version_bound and current) else None
        with self.write() as db:
            db.execute(
                "INSERT INTO library_metadata (metadata_id, library_object_id, version_id, key, value, value_type) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT (library_object_id, ifnull(version_id, ''), key) "
                "DO UPDATE SET value = excluded.value, value_type = excluded.value_type",
                (_id("md_"), obj["library_object_id"], version_id, key, value, value_type),
            )

    def metadata(self, object_code: str) -> Dict[str, str]:
        return {
            r["key"]: r["value"] for r in self._all(
                "SELECT m.key, m.value FROM library_metadata m JOIN library_object o USING (library_object_id) "
                "WHERE o.object_code = ? ORDER BY m.version_id IS NOT NULL, m.key",
                (object_code,),
            )
        }

    def add_source_ref(self, ref_kind: str, reference: str, *, version_id: Optional[str] = None,
                       candidate_id: Optional[str] = None, note: str = "") -> str:
        ref_id = _id("src_")
        with self.write() as db:
            db.execute(
                "INSERT INTO source_ref (source_ref_id, version_id, candidate_id, ref_kind, reference, note) "
                "VALUES (?,?,?,?,?,?)",
                (ref_id, version_id, candidate_id, ref_kind, reference, note),
            )
        return ref_id

    def source_refs(self, *, version_id: Optional[str] = None, candidate_id: Optional[str] = None) -> List[sqlite3.Row]:
        if version_id:
            return self._all("SELECT * FROM source_ref WHERE version_id = ?", (version_id,))
        return self._all("SELECT * FROM source_ref WHERE candidate_id = ?", (candidate_id,))

    def link_archive(self, object_code: str, archive_record_id: str, relationship_type: str = "ARCHIVE_RECORD",
                     *, version_id: Optional[str] = None, approval_record_id: Optional[str] = None,
                     description: str = "") -> str:
        obj = self.object_row(object_code)
        if obj is None:
            raise NotFound(object_code)
        link_id = _id("arl_")
        with self.write() as db:
            db.execute(
                "INSERT INTO archive_link (archive_link_id, library_object_id, version_id, approval_record_id, "
                "archive_record_id, relationship_type, description, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (link_id, obj["library_object_id"], version_id, approval_record_id, archive_record_id,
                 relationship_type, description, _now()),
            )
        return link_id

    def relate(self, from_code: str, to_code: str, relationship_type: str) -> str:
        a, b = self.object_row(from_code), self.object_row(to_code)
        if a is None or b is None:
            raise NotFound(from_code if a is None else to_code)
        rel_id = _id("rel_")
        with self.write() as db:
            db.execute(
                "INSERT INTO object_relationship (relationship_id, from_object_id, to_object_id, relationship_type, "
                "active, created_at) VALUES (?,?,?,?,1,?)",
                (rel_id, a["library_object_id"], b["library_object_id"], relationship_type, _now()),
            )
        return rel_id

    def relationships(self, object_code: str) -> List[sqlite3.Row]:
        return self._all(
            "SELECT r.relationship_type, f.object_code AS from_code, t.object_code AS to_code, r.active "
            "FROM object_relationship r JOIN library_object f ON f.library_object_id = r.from_object_id "
            "JOIN library_object t ON t.library_object_id = r.to_object_id "
            "WHERE f.object_code = ? OR t.object_code = ? ORDER BY r.created_at",
            (object_code, object_code),
        )

    def set_tags(self, object_code: str, tags: Iterable[str]) -> None:
        obj = self.object_row(object_code)
        if obj is None:
            raise NotFound(object_code)
        with self.write() as db:
            db.execute("DELETE FROM library_object_tag WHERE library_object_id = ?", (obj["library_object_id"],))
            for position, tag in enumerate(dict.fromkeys(tags)):
                db.execute("INSERT INTO library_object_tag VALUES (?,?,?)", (obj["library_object_id"], tag, position))

    def tags(self, object_code: str) -> List[str]:
        return [r[0] for r in self._all(
            "SELECT t.tag FROM library_object_tag t JOIN library_object o USING (library_object_id) "
            "WHERE o.object_code = ? ORDER BY t.position", (object_code,))]

    # ── retrieval ────────────────────────────────────────────────────────

    def record_retrieval(self, consumer_role: str, requested_object_code: str, outcome: str, *,
                         library_object_id: Optional[str] = None, version_id: Optional[str] = None,
                         purpose: str = "", current_only: bool = True) -> None:
        with self.write() as db:
            db.execute(
                "INSERT INTO retrieval_event (consumer_role, requested_object_code, library_object_id, version_id, "
                "purpose, current_only, outcome, retrieved_at) VALUES (?,?,?,?,?,?,?,?)",
                (consumer_role, requested_object_code, library_object_id, version_id, purpose,
                 1 if current_only else 0, outcome, _now()),
            )

    def retrieve(self, object_code: str, *, consumer_role: str, purpose: str = "",
                 for_external_use: bool = True) -> Tuple[Optional[sqlite3.Row], str]:
        """The current version for a consumer, and the outcome recorded for it.

        For external use a REVIEW_DUE version is not handed out: the outcome is
        BLOCKED_REVIEW_DUE and the row is None, so a consumer that only checks for None cannot
        publish an expired credential by mistake.
        """
        row = self.current_row(object_code)
        if row is None:
            self.record_retrieval(consumer_role, object_code, "MISSING", purpose=purpose, current_only=True)
            return None, "MISSING"
        if for_external_use and row["lifecycle_state"] == LifecycleState.REVIEW_DUE.value:
            self.record_retrieval(consumer_role, object_code, "BLOCKED_REVIEW_DUE",
                                  library_object_id=row["library_object_id"],
                                  version_id=row["current_version_id"], purpose=purpose, current_only=True)
            return None, "BLOCKED_REVIEW_DUE"
        self.record_retrieval(consumer_role, object_code, "RETURNED", library_object_id=row["library_object_id"],
                              version_id=row["current_version_id"], purpose=purpose,
                              current_only=for_external_use)
        return row, "RETURNED"

    def retrieval_events(self, object_code: Optional[str] = None) -> List[sqlite3.Row]:
        if object_code:
            return self._all("SELECT * FROM retrieval_event WHERE requested_object_code = ? ORDER BY retrieval_id",
                             (object_code,))
        return self._all("SELECT * FROM retrieval_event ORDER BY retrieval_id")

    # ── notices ──────────────────────────────────────────────────────────

    def raise_notice(self, notice_type: str, **kwargs) -> str:
        with self.write():
            return self._raise_notice_in_txn(notice_type, **kwargs)

    def _raise_notice_in_txn(self, notice_type: str, *, relative_path: Optional[str] = None,
                             candidate_id: Optional[str] = None, library_object_id: Optional[str] = None,
                             version_id: Optional[str] = None, scan_id: Optional[int] = None,
                             missing_field: Optional[str] = None, recommended_object_type: Optional[str] = None,
                             recommended_action: str = "", detail: str = "") -> str:
        """One OPEN notice per subject and kind: raising the same one again returns it."""
        existing = self._one(
            "SELECT notice_id FROM library_notice WHERE status = 'OPEN' AND notice_type = ? "
            "AND relative_path IS ? AND candidate_id IS ? AND library_object_id IS ? AND version_id IS ? "
            "AND missing_field IS ?",
            (notice_type, relative_path, candidate_id, library_object_id, version_id, missing_field),
        )
        if existing:
            return existing["notice_id"]
        notice_id = _id("ntc_")
        self.db.execute(
            "INSERT INTO library_notice (notice_id, notice_type, relative_path, candidate_id, library_object_id, "
            "version_id, scan_id, missing_field, recommended_object_type, recommended_action, detail, raised_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (notice_id, notice_type, relative_path, candidate_id, library_object_id, version_id, scan_id,
             missing_field, recommended_object_type, recommended_action, detail, _now()),
        )
        return notice_id

    def notices(self, status: Optional[str] = "OPEN", notice_type: Optional[str] = None) -> List[sqlite3.Row]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if notice_type:
            clauses.append("notice_type = ?"); params.append(notice_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._all(f"SELECT * FROM library_notice{where} ORDER BY raised_at", params)

    def resolve_notice(self, notice_id: str, resolved_by: str, resolution: str) -> sqlite3.Row:
        if normalize_identity(resolved_by) in NOTICE_RESOLVER_REFUSED:
            raise CatalogRefusal(
                f"{resolved_by!r} may not settle a Library notice. Library raises notices and recommends; "
                "a human or an authorised source settles them."
            )
        if not resolution or not resolution.strip():
            raise CatalogRefusal("a resolution says what was decided")
        with self.write() as db:
            cursor = db.execute(
                "UPDATE library_notice SET status = 'RESOLVED', resolved_by = ?, resolved_at = ?, resolution = ? "
                "WHERE notice_id = ? AND status = 'OPEN'",
                (resolved_by.strip(), _now(), resolution.strip(), notice_id),
            )
            if cursor.rowcount == 0:
                raise NotFound(f"no open notice {notice_id}")
        return self._one("SELECT * FROM library_notice WHERE notice_id = ?", (notice_id,))

    # ── candidates ───────────────────────────────────────────────────────

    def candidate_row(self, candidate_id: str) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM library_candidate WHERE candidate_id = ?", (candidate_id,))

    def candidates(self, statuses: Optional[Sequence[str]] = None) -> List[sqlite3.Row]:
        if statuses:
            marks = ",".join("?" for _ in statuses)
            return self._all(
                f"SELECT * FROM library_candidate WHERE status IN ({marks}) ORDER BY created_at, candidate_id",
                list(statuses),
            )
        return self._all("SELECT * FROM library_candidate ORDER BY created_at, candidate_id")

    def submit_candidate(
        self,
        *,
        submitted_by_role: str,
        source_type: str,
        collection: str,
        proposed_object_code: str,
        proposed_title: str,
        proposed_body_or_reference: str,
        source_finding_id: Optional[str] = None,
        submitted_by_name: Optional[str] = None,
        mission_record_id: Optional[str] = None,
        workflow_event_id: Optional[str] = None,
        proposed_object_type: Optional[str] = None,
        candidate_id: Optional[str] = None,
        created_at: Optional[str] = None,
        source_refs: Iterable[Tuple[str, str]] = (),
    ) -> sqlite3.Row:
        """SUBMITTED, then PENDING_REVIEW, in one transaction.

        A type the submitter supplies is the submitter's confirmation of it (the submitting
        source is an authorised confirmer, ruling 3). Library never submits (ruling 5).
        """
        role = normalize_identity(submitted_by_role)
        if role not in CANDIDATE_SOURCES:
            raise CatalogRefusal(
                f"{submitted_by_role!r} may not nominate a Library candidate. Candidates come from a human, "
                "Intelligence, Publisher, or a Dispatch workflow tied to a Mission Record or workflow event; "
                "Library may not nominate to itself."
            )
        require_valid_collection(collection)
        if role == "HUMAN":
            submitted_by_name = self.require_human(submitted_by_name, "submitted_by_name")
        if role == "DISPATCH" and not (mission_record_id or workflow_event_id):
            raise CatalogRefusal("a Dispatch candidate must name the Mission Record or workflow event it came from")
        if proposed_object_type is not None and proposed_object_type not in OBJECT_TYPES:
            raise CatalogRefusal(f"object_type {proposed_object_type!r} is not one of the Core Object Model types")

        candidate_id = candidate_id or str(uuid.uuid4())
        created_at = created_at or _now()
        confirmed_by = (submitted_by_name if role == "HUMAN" else role) if proposed_object_type else None
        with self.write() as db:
            db.execute(
                "INSERT INTO library_candidate (candidate_id, submitted_by_role, submitted_by_name, mission_record_id, "
                "workflow_event_id, source_type, proposed_object_type, object_type_confirmed_by, "
                "object_type_confirmed_at, proposed_collection_id, proposed_object_code, proposed_title, "
                "proposed_body_or_reference, source_finding_id, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'SUBMITTED', ?)",
                (candidate_id, role, submitted_by_name, mission_record_id, workflow_event_id, source_type,
                 proposed_object_type, confirmed_by, created_at if confirmed_by else None, collection,
                 proposed_object_code, proposed_title, proposed_body_or_reference, source_finding_id, created_at),
            )
            db.execute("UPDATE library_candidate SET status = 'PENDING_REVIEW' WHERE candidate_id = ?", (candidate_id,))
            refs = list(source_refs)
            if source_finding_id:
                refs.append(("INTELLIGENCE_FINDING", source_finding_id))
            if mission_record_id:
                refs.append(("MISSION_RECORD", mission_record_id))
            if workflow_event_id:
                refs.append(("WORKFLOW_EVENT", workflow_event_id))
            for kind, reference in dict.fromkeys(refs):
                db.execute(
                    "INSERT INTO source_ref (source_ref_id, candidate_id, ref_kind, reference) VALUES (?,?,?,?)",
                    (_id("src_"), candidate_id, kind, reference),
                )
        return self.candidate_row(candidate_id)

    def classify_candidate(self, candidate_id: str, recommended_object_type: str) -> sqlite3.Row:
        """Library's classification. A recommendation; it confirms nothing."""
        if recommended_object_type not in OBJECT_TYPES:
            raise CatalogRefusal(f"object_type {recommended_object_type!r} is not one of the Core Object Model types")
        with self.write() as db:
            if db.execute("UPDATE library_candidate SET recommended_object_type = ? WHERE candidate_id = ?",
                          (recommended_object_type, candidate_id)).rowcount == 0:
                raise NotFound(candidate_id)
        return self.candidate_row(candidate_id)

    def confirm_object_type(self, candidate_id: str, object_type: str, confirmed_by: str) -> sqlite3.Row:
        """A human, or the source that submitted the candidate, says what the asset is."""
        row = self.candidate_row(candidate_id)
        if row is None:
            raise NotFound(candidate_id)
        if object_type not in OBJECT_TYPES:
            raise CatalogRefusal(f"object_type {object_type!r} is not one of the Core Object Model types")
        who = normalize_identity(confirmed_by)
        if not (row["submitted_by_role"] != "HUMAN" and who == row["submitted_by_role"]):
            if who in ("LIBRARY",):
                raise CatalogRefusal("Library recommends a type; it may not confirm one (ruling 5)")
            self.require_human(confirmed_by, "confirmed_by")
        with self.write() as db:
            db.execute(
                "UPDATE library_candidate SET proposed_object_type = ?, object_type_confirmed_by = ?, "
                "object_type_confirmed_at = ? WHERE candidate_id = ?",
                (object_type, confirmed_by.strip(), _now(), candidate_id),
            )
        return self.candidate_row(candidate_id)

    def validate_candidate(self, candidate_id: str) -> Tuple[bool, List[str]]:
        """Library's validation gate. Passes to VALIDATED, or records why not and raises notices."""
        row = self.candidate_row(candidate_id)
        if row is None:
            raise NotFound(candidate_id)
        if row["status"] != "PENDING_REVIEW":
            raise CatalogRefusal(f"candidate {candidate_id} is {row['status']}; only PENDING_REVIEW is validated")
        problems: List[str] = []
        if not row["object_type_confirmed_by"]:
            problems.append("object_type is not confirmed by a human or the submitting source")
        if not (row["proposed_body_or_reference"] or "").strip():
            problems.append("the candidate carries no body or reference")
        has_source = row["submitted_by_role"] == "HUMAN" or row["source_finding_id"] or self.source_refs(candidate_id=candidate_id)
        if not has_source:
            problems.append("no source is recorded (source trace check)")
        existing = self.object_row(row["proposed_object_code"])
        if existing is not None and row["proposed_object_type"] and (
            existing["object_type"] != row["proposed_object_type"] or existing["collection_id"] != row["proposed_collection_id"]
        ):
            problems.append(
                f"{row['proposed_object_code']} already exists as {existing['object_type']} in "
                f"{existing['collection_id']}"
            )

        with self.write() as db:
            if problems:
                db.execute("UPDATE library_candidate SET validation_result = 'FAILED', validated_at = ? WHERE candidate_id = ?",
                           (_now(), candidate_id))
                if not row["object_type_confirmed_by"]:
                    self._raise_notice_in_txn(
                        "MISSING_FIELD", candidate_id=candidate_id, missing_field="object_type",
                        recommended_object_type=row["recommended_object_type"],
                        recommended_action="The submitting source or a human confirms the object type.",
                        detail=f"Candidate {row['proposed_object_code']} cannot be validated without a confirmed type.",
                    )
                other = [p for p in problems if not p.startswith("object_type")]
                if other:
                    self._raise_notice_in_txn(
                        "CONFLICT", candidate_id=candidate_id,
                        recommended_action="Correct the candidate and submit it again.",
                        detail="; ".join(other),
                    )
                self._raise_notice_in_txn(
                    "BLOCKED_WORK", candidate_id=candidate_id,
                    recommended_action="Resolve the notices on this candidate; it cannot reach a human decision yet.",
                    detail=f"Validation of {row['proposed_object_code']} failed: {'; '.join(problems)}",
                )
                return False, problems
            db.execute(
                "UPDATE library_candidate SET status = 'VALIDATED', validation_result = 'PASSED', validated_at = ? "
                "WHERE candidate_id = ?",
                (_now(), candidate_id),
            )
            # Notices this candidate raised earlier were cleared by the confirmation, not by Library.
            # They are closed in the confirmer's name, saying so; Library settles nothing itself.
            db.execute(
                "UPDATE library_notice SET status = 'RESOLVED', resolved_by = ?, resolved_at = ?, resolution = ? "
                "WHERE candidate_id = ? AND status = 'OPEN' AND notice_type IN ('MISSING_FIELD', 'BLOCKED_WORK')",
                (row["object_type_confirmed_by"], _now(),
                 f"cleared when {row['object_type_confirmed_by']} confirmed the object type as "
                 f"{row['proposed_object_type']}; validation then passed",
                 candidate_id),
            )
        return True, []

    def decide_candidate(self, candidate_id: str, decision: str, reviewed_by: str, *,
                         capture_channel: Optional[str] = None, capture_ref: Optional[str] = None,
                         notes: str = "") -> sqlite3.Row:
        """The human decision: APPROVED (into a CURRENT version), REJECTED or DEFERRED."""
        decision = decision.upper()
        if decision not in ("APPROVED", "REJECTED", "DEFERRED"):
            raise CatalogRefusal(f"{decision!r} is not a decision")
        person = self.require_human(reviewed_by, "reviewed_by")
        row = self.candidate_row(candidate_id)
        if row is None:
            raise NotFound(candidate_id)
        if decision == "APPROVED" and row["status"] != "VALIDATED":
            raise CatalogRefusal(
                f"candidate {candidate_id} is {row['status']}. A worker-nominated candidate is validated by "
                "Library before a human approves it (SUBMITTED -> PENDING_REVIEW -> VALIDATED -> APPROVED)."
            )
        if decision != "APPROVED" and row["status"] not in ("PENDING_REVIEW", "VALIDATED"):
            raise CatalogRefusal(f"candidate {candidate_id} is {row['status']} and awaits no decision")
        now = _now()
        with self.write() as db:
            approval_id = _id("apr_")
            if decision == "APPROVED":
                existing = self.object_row(row["proposed_object_code"])
                if existing is None:
                    library_object_id = _id("libobj_")
                    db.execute(
                        "INSERT INTO library_object (library_object_id, object_code, object_type, collection_id, title, "
                        "slug, canonical_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (library_object_id, row["proposed_object_code"], row["proposed_object_type"],
                         row["proposed_collection_id"], row["proposed_title"], _slug(row["proposed_object_code"]),
                         row["proposed_title"], now, now),
                    )
                else:
                    library_object_id = existing["library_object_id"]
                major, minor = self._next_version(library_object_id if existing else None, False)
                supersedes = self._flip_current(library_object_id)
                version_id = _id("libver_")
                db.execute(
                    "INSERT INTO approval_record (approval_record_id, library_object_id, version_id, candidate_id, "
                    "approver, approval_status, approval_basis, capture_channel, capture_ref, approved_at, notes) "
                    "VALUES (?,?,?,?,?, 'APPROVED', 'CANDIDATE_REVIEW', ?,?,?,?)",
                    (approval_id, library_object_id, version_id, candidate_id, person, capture_channel,
                     capture_ref, now, notes),
                )
                db.execute(
                    "INSERT INTO library_version (version_id, library_object_id, version_major, version_minor, "
                    "lifecycle_state, title, content_uri, body, supersedes_version_id, approval_record_id, "
                    "validation_result, created_at) VALUES (?,?,?,?, 'CURRENT', ?,?,?,?,?, 'PASSED', ?)",
                    (version_id, library_object_id, major, minor, row["proposed_title"],
                     f"candidate:{candidate_id}", row["proposed_body_or_reference"], supersedes, approval_id, now),
                )
                for ref in self.source_refs(candidate_id=candidate_id):
                    db.execute(
                        "INSERT INTO source_ref (source_ref_id, version_id, ref_kind, reference, note) VALUES (?,?,?,?,?)",
                        (_id("src_"), version_id, ref["ref_kind"], ref["reference"], ref["note"]),
                    )
                self._queue_retention(library_object_id, now)
            else:
                db.execute(
                    "INSERT INTO approval_record (approval_record_id, candidate_id, approver, approval_status, "
                    "approval_basis, capture_channel, capture_ref, approved_at, notes) "
                    "VALUES (?,?,?,?, 'CANDIDATE_REVIEW', ?,?,?,?)",
                    (approval_id, candidate_id, person, decision, capture_channel, capture_ref, now, notes),
                )
            db.execute(
                "UPDATE library_candidate SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE candidate_id = ?",
                (decision, person, now, candidate_id),
            )
        return self.candidate_row(candidate_id)

    def resubmit_deferred(self, candidate_id: str) -> sqlite3.Row:
        with self.write() as db:
            if db.execute(
                "UPDATE library_candidate SET status = 'PENDING_REVIEW', reviewed_by = NULL, reviewed_at = NULL, "
                "validation_result = 'NOT_RUN', validated_at = NULL WHERE candidate_id = ? AND status = 'DEFERRED'",
                (candidate_id,),
            ).rowcount == 0:
                raise CatalogRefusal(f"candidate {candidate_id} is not DEFERRED")
        return self.candidate_row(candidate_id)

    # ── recipes ──────────────────────────────────────────────────────────

    def load_recipes(self, path: Path) -> Dict[str, List[str]]:
        """Persist `publisher_recipes.json`. Idempotent: an unchanged file changes nothing.

        A changed recipe supersedes the current one as a new version. Types the file does not
        define get a placeholder if they have nothing at all. A type the file no longer defines
        keeps its current recipe and is reported, not silently removed.
        """
        from dispatch_library.models import RecipeType
        from dispatch_library.recipes import parse_publisher_recipes

        path = Path(path)
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        loaded = parse_publisher_recipes(json.loads(raw.decode("utf-8")), str(path))
        report: Dict[str, List[str]] = {"loaded": [], "unchanged": [], "placeholders": [], "not_in_file": []}
        now = _now()
        with self.write() as db:
            in_file = set()
            for recipe, detail in loaded:
                rtype = recipe.recipe_type.value
                in_file.add(rtype)
                current = db.execute(
                    "SELECT * FROM publisher_recipe WHERE recipe_type = ? AND status = 'CURRENT'", (rtype,)
                ).fetchone()
                incoming = {
                    "recipe_name": detail.recipe_name, "source_key": detail.source_key,
                    "human_review_required": detail.human_review_required,
                    "required_library_object_codes": list(recipe.required_library_object_codes),
                    "required_publisher_parts": list(recipe.required_publisher_parts),
                    "required_human_items": list(detail.required_human_items),
                    "required_outputs": list(detail.required_outputs),
                    "required_intelligence_requirement_types": list(recipe.required_intelligence_requirement_types),
                }
                # Compared recipe by recipe, not by file hash: editing one recipe in the file must
                # not re-version the others. An unchanged recipe keeps the hash it was loaded from.
                if current is not None and not current["is_placeholder"]:
                    existing = self.recipe(rtype)
                    if all(existing[k] == v for k, v in incoming.items()):
                        report["unchanged"].append(rtype)
                        continue
                version = (db.execute("SELECT max(version) FROM publisher_recipe WHERE recipe_type = ?",
                                      (rtype,)).fetchone()[0] or 0) + 1
                if current is not None:
                    db.execute("UPDATE publisher_recipe SET status = 'SUPERSEDED' WHERE recipe_id = ?",
                               (current["recipe_id"],))
                recipe_id = _id("rcp_")
                db.execute(
                    "INSERT INTO publisher_recipe (recipe_id, recipe_code, recipe_type, version, status, is_placeholder, "
                    "recipe_name, source_key, human_review_required, source_path, source_sha256, loaded_at) "
                    "VALUES (?,?,?,?, 'CURRENT', 0, ?,?,?,?,?,?)",
                    (recipe_id, f"RECIPE-{rtype}-v{version}", rtype, version, detail.recipe_name, detail.source_key,
                     1 if detail.human_review_required else 0, str(path), digest, now),
                )
                for kind, values in (("COMPANY_ITEM", recipe.required_library_object_codes),
                                     ("PUBLISHER_ITEM", recipe.required_publisher_parts),
                                     ("HUMAN_ITEM", detail.required_human_items),
                                     ("OUTPUT", detail.required_outputs),
                                     ("INTELLIGENCE_REQUIREMENT", recipe.required_intelligence_requirement_types)):
                    for position, value in enumerate(values):
                        db.execute("INSERT INTO recipe_requirement VALUES (?,?,?,?)", (recipe_id, kind, value, position))
                report["loaded"].append(rtype)
            for rtype in (t.value for t in RecipeType):
                if rtype in in_file:
                    continue
                current = db.execute("SELECT is_placeholder FROM publisher_recipe WHERE recipe_type = ? AND status = 'CURRENT'",
                                     (rtype,)).fetchone()
                if current is None:
                    db.execute(
                        "INSERT INTO publisher_recipe (recipe_id, recipe_code, recipe_type, version, status, "
                        "is_placeholder, loaded_at) VALUES (?,?,?,1,'CURRENT',1,?)",
                        (_id("rcp_"), f"RECIPE-{rtype}-v1", rtype, now),
                    )
                    report["placeholders"].append(rtype)
                elif not current["is_placeholder"]:
                    report["not_in_file"].append(rtype)
        return report

    def recipe(self, recipe_type: str) -> Optional[Dict[str, object]]:
        row = self._one("SELECT * FROM publisher_recipe WHERE recipe_type = ? AND status = 'CURRENT'", (str(recipe_type),))
        if row is None:
            return None
        requirements: Dict[str, List[str]] = {}
        for req in self._all("SELECT kind, value FROM recipe_requirement WHERE recipe_id = ? ORDER BY kind, position",
                             (row["recipe_id"],)):
            requirements.setdefault(req["kind"], []).append(req["value"])
        return {
            "recipe_code": row["recipe_code"],
            "recipe_type": row["recipe_type"],
            "version": row["version"],
            "status": row["status"],
            "is_placeholder": bool(row["is_placeholder"]),
            "recipe_name": row["recipe_name"],
            "source_key": row["source_key"],
            "source_path": row["source_path"],
            "source_sha256": row["source_sha256"],
            "human_review_required": None if row["human_review_required"] is None else bool(row["human_review_required"]),
            "required_library_object_codes": requirements.get("COMPANY_ITEM", []),
            "required_publisher_parts": requirements.get("PUBLISHER_ITEM", []),
            "required_human_items": requirements.get("HUMAN_ITEM", []),
            "required_outputs": requirements.get("OUTPUT", []),
            "required_intelligence_requirement_types": requirements.get("INTELLIGENCE_REQUIREMENT", []),
            "loaded_at": row["loaded_at"],
        }

    def recipes(self) -> List[Dict[str, object]]:
        return [self.recipe(r[0]) for r in self._all(
            "SELECT recipe_type FROM publisher_recipe WHERE status = 'CURRENT' ORDER BY recipe_type")]

    # ── the shelf ────────────────────────────────────────────────────────

    def scan(self, memory_root: Optional[Path] = None, *, record: bool = True) -> ScanReport:
        """Compare the shelf with the catalog. Opens shelf files to hash them; writes none.

        UNCATALOGUED, CHANGED and MISSING compare files with current versions. UNMAPPED_FOLDER
        and PLACEMENT_CONFLICT apply the approved folder mapping (shelf_mapping). `record=False`
        is the dry run: identical findings, nothing written anywhere.
        """
        from dispatch_library import shelf_mapping

        root = Path(memory_root or self.memory_root or "")
        if not root.is_dir():
            raise CatalogRefusal(f"memory root {root} is not a directory")
        started = _now()
        report = ScanReport(scan_id=None, memory_root=str(root))

        bound = {
            r["relative_path"].casefold(): r for r in self._all(
                "SELECT o.object_code, o.library_object_id, v.version_id, v.relative_path, v.content_sha256 "
                "FROM library_version v JOIN library_object o USING (library_object_id) "
                "WHERE v.is_current = 1 AND v.relative_path IS NOT NULL"
            )
        }
        seen = set()
        matched: List[Tuple[str, str]] = []  # (version_id, observed sha)
        for entry in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if entry.is_dir() and not is_ignorable(PurePosixPath(entry.name)):
                report.folders_seen += 1
                mapping = shelf_mapping.mapping_for(entry.name)
                if mapping is None or mapping.basis is shelf_mapping.MappingBasis.UNMAPPED:
                    detail = mapping.citation if mapping else "folder is not in the approved mapping"
                    report.findings.append(("UNMAPPED_FOLDER", entry.name, detail))
        for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix().casefold()):
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if is_ignorable(rel):
                continue
            report.files_seen += 1
            key = rel.as_posix().casefold()
            seen.add(key)
            row = bound.get(key)
            if row is None:
                report.findings.append(("UNCATALOGUED", rel.as_posix(), "on the shelf; no Library object stands for it"))
                continue
            report.catalogued += 1
            digest = sha256_of(path)
            if digest != row["content_sha256"]:
                report.findings.append((
                    "CHANGED", rel.as_posix(),
                    f"{row['object_code']} recorded {row['content_sha256'][:12]}, file is {digest[:12]}",
                ))
            else:
                matched.append((row["version_id"], digest))
        for key, row in sorted(bound.items()):
            if key not in seen:
                report.findings.append(("MISSING", row["relative_path"], f"{row['object_code']} stands for a file that is not there"))
        for conflict in shelf_mapping.PLACEMENT_CONFLICTS:
            if (root / conflict.relative_path).is_file():
                target = conflict.recommended_collection or "Archive referral"
                report.findings.append(("PLACEMENT_CONFLICT", conflict.relative_path,
                                        f"{conflict.kind}; recommended {target} (recommendation only)"))

        if not record:
            return report

        mapping_version = self._one(
            "SELECT current_version_id FROM library_current WHERE object_type = 'LIBRARY_INDEX_MANIFEST' "
            "AND collection_id = 'Index' ORDER BY object_code LIMIT 1"
        )
        now = _now()
        with self.write() as db:
            cursor = db.execute(
                "INSERT INTO catalog_scan (started_at, memory_root, files_seen, folders_seen, mapping_version_id) "
                "VALUES (?,?,?,?,?)",
                (started, str(root), report.files_seen, report.folders_seen,
                 mapping_version["current_version_id"] if mapping_version else None),
            )
            scan_id = int(cursor.lastrowid)
            for kind, rel, detail in report.findings:
                version_id = None
                if kind in ("CHANGED", "MISSING"):
                    row = bound[rel.casefold()]
                    version_id = row["version_id"]
                    db.execute("UPDATE library_version SET drift_check_result = 'FAILED' WHERE version_id = ?", (version_id,))
                    self._raise_notice_in_txn(
                        kind, version_id=version_id, library_object_id=row["library_object_id"], scan_id=scan_id,
                        recommended_action=("Place the changed file as a new version, or restore the recorded one."
                                            if kind == "CHANGED" else "Find the file or record where it went."),
                        detail=detail,
                    )
                db.execute(
                    "INSERT OR IGNORE INTO catalog_finding (scan_id, relative_path, finding, version_id, detail) "
                    "VALUES (?,?,?,?,?)",
                    (scan_id, rel, kind, version_id, detail),
                )
            for version_id, _digest in matched:
                db.execute("UPDATE library_version SET drift_check_result = 'PASSED', observed_at = ? WHERE version_id = ?",
                           (now, version_id))
            db.execute("UPDATE catalog_scan SET finished_at = ? WHERE scan_id = ?", (_now(), scan_id))
        report.scan_id = scan_id
        return report

    def scan_summary(self, scan_id: int) -> Optional[sqlite3.Row]:
        return self._one("SELECT * FROM catalog_scan_summary WHERE scan_id = ?", (scan_id,))

    # ── status ───────────────────────────────────────────────────────────

    def counts(self) -> Dict[str, int]:
        tables = ("library_object", "library_version", "approval_record", "library_candidate", "library_notice",
                  "publisher_recipe", "retrieval_event", "catalog_scan", "archive_review_queue")
        return {t: self._one(f"SELECT count(*) FROM {t}")[0] for t in tables}
