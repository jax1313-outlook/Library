-- Library catalog, schema version 1.
--
-- The database is the catalog. The shelf -- DISPATCH_MEMORY_ROOT -- holds the
-- assets themselves, and nothing here moves, renames or rewrites them. For a
-- shelf-backed object `body_or_uri` carries the relative path and the bytes
-- stay where a human put them.
--
-- Constraints here duplicate rules already enforced in models.py and
-- ingestion.py. That duplication is deliberate: the Python rules protect the
-- objects this package constructs, and these protect the database from anything
-- that ever writes to it without going through them.
--
-- PRAGMA journal_mode is NOT set here. It does not honour busy_timeout, so it
-- is issued once at connect time in connection.py where the timeout is in
-- force.

PRAGMA foreign_keys = ON;

CREATE TABLE library_object (
    object_code        TEXT    NOT NULL,
    version            INTEGER NOT NULL,
    collection         TEXT    NOT NULL,
    title              TEXT    NOT NULL,
    status             TEXT    NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED','DRAFT_CANDIDATE')),
    source             TEXT    NOT NULL CHECK (source IN ('HUMAN_PLACED','APPROVED_CANDIDATE')),
    body_or_uri        TEXT    NOT NULL,
    accepted_by        TEXT    NOT NULL,
    accepted_at        TEXT    NOT NULL,
    supersedes_version INTEGER,

    -- The shelf. NULL for an object whose body is inline rather than a file.
    relative_path      TEXT,      -- under DISPATCH_MEMORY_ROOT, POSIX separators
    content_sha256     TEXT,
    size_bytes         INTEGER,
    observed_at        TEXT,      -- when the catalog last verified the file

    PRIMARY KEY (object_code, version),
    CHECK (version > 0),
    CHECK (accepted_by <> ''),
    -- The Hard Rule, in the database rather than only in Python: no system
    -- identity may stand as an approval.
    CHECK (upper(trim(accepted_by)) NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','SYSTEM','AUTOMATION'))
);

-- The resolver's correctness condition. Today it is guaranteed by one careful
-- function; here it is guaranteed by SQLite.
CREATE UNIQUE INDEX library_object_one_current
    ON library_object (object_code) WHERE status = 'CURRENT';

-- One current object per shelf file. Two objects claiming the same document is
-- a cataloguing error, and better refused at write time than discovered by a
-- Publisher packet that resolves twice.
CREATE UNIQUE INDEX library_object_path
    ON library_object (relative_path)
    WHERE relative_path IS NOT NULL AND status = 'CURRENT';

CREATE INDEX library_object_shelf ON library_object (collection, status);

CREATE TABLE library_object_tag (
    object_code TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    tag         TEXT    NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (object_code, version, tag),
    FOREIGN KEY (object_code, version)
        REFERENCES library_object (object_code, version) ON DELETE CASCADE
);

CREATE TABLE library_candidate (
    candidate_id               TEXT PRIMARY KEY,
    submitted_by               TEXT NOT NULL CHECK (submitted_by IN ('INTELLIGENCE','PUBLISHER')),
    source_type                TEXT NOT NULL,
    collection                 TEXT NOT NULL,
    proposed_object_code       TEXT NOT NULL,
    proposed_title             TEXT NOT NULL,
    proposed_body_or_reference TEXT NOT NULL,
    source_finding_id          TEXT,
    status                     TEXT NOT NULL CHECK (status IN ('PENDING_REVIEW','APPROVED','REJECTED')),
    reviewed_by                TEXT,
    reviewed_at                TEXT,
    created_at                 TEXT NOT NULL,

    -- A reviewed candidate has a reviewer; a pending one does not. Keeps a
    -- decision from existing without a name attached to it.
    CHECK ((status =  'PENDING_REVIEW' AND reviewed_by IS NULL)
        OR (status <> 'PENDING_REVIEW' AND reviewed_by IS NOT NULL)),
    -- Publisher and Intelligence may not approve their own nominations.
    CHECK (reviewed_by IS NULL OR upper(trim(reviewed_by)) <> submitted_by),
    CHECK (reviewed_by IS NULL OR upper(trim(reviewed_by)) NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','SYSTEM','AUTOMATION'))
);

CREATE INDEX library_candidate_pending ON library_candidate (status, created_at);

CREATE TABLE publisher_recipe (
    recipe_code TEXT PRIMARY KEY,
    recipe_type TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED'))
);

CREATE UNIQUE INDEX publisher_recipe_one_current
    ON publisher_recipe (recipe_type) WHERE status = 'CURRENT';

CREATE TABLE recipe_requirement (
    recipe_code TEXT    NOT NULL REFERENCES publisher_recipe (recipe_code) ON DELETE CASCADE,
    kind        TEXT    NOT NULL CHECK (kind IN ('LIBRARY_OBJECT','PUBLISHER_PART','INTELLIGENCE_REQUIREMENT')),
    value       TEXT    NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (recipe_code, kind, value)
);

-- ARCHIVE_REVIEW_POLICY.md sections 2-4: current plus three previous are
-- retained automatically; older versions queue for Mike's Keep/Delete decision.
-- Nothing is ever deleted by this table. It prepares a decision; it does not
-- make one.
CREATE TABLE archive_review_queue (
    object_code TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    queued_at   TEXT    NOT NULL,
    disposition TEXT    NOT NULL DEFAULT 'PENDING'
                CHECK (disposition IN ('PENDING','KEEP','DELETE')),
    decided_by  TEXT,
    decided_at  TEXT,
    PRIMARY KEY (object_code, version),
    FOREIGN KEY (object_code, version)
        REFERENCES library_object (object_code, version) ON DELETE CASCADE,
    CHECK ((disposition =  'PENDING' AND decided_by IS NULL)
        OR (disposition <> 'PENDING' AND decided_by IS NOT NULL))
);

-- Every scan of the shelf, so drift is a record rather than a console message.
CREATE TABLE catalog_scan (
    scan_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT,
    memory_root  TEXT    NOT NULL,
    files_seen   INTEGER NOT NULL DEFAULT 0,
    catalogued   INTEGER NOT NULL DEFAULT 0,
    uncatalogued INTEGER NOT NULL DEFAULT 0,
    changed      INTEGER NOT NULL DEFAULT 0,  -- hash differs from the catalog
    missing      INTEGER NOT NULL DEFAULT 0   -- catalogued, file not on the shelf
);

CREATE TABLE catalog_finding (
    scan_id       INTEGER NOT NULL REFERENCES catalog_scan (scan_id) ON DELETE CASCADE,
    relative_path TEXT    NOT NULL,
    finding       TEXT    NOT NULL CHECK (finding IN ('UNCATALOGUED','CHANGED','MISSING')),
    detail        TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (scan_id, relative_path, finding)
);

CREATE TABLE schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT    NOT NULL
);
