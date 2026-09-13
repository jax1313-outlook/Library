-- Library catalog, schema version 2.
--
-- Copied verbatim from LIBRARY_IMPLEMENTATION_PLAN_v2.md section 2, approved by Mike
-- Zachary at commit 9747b74. tests/test_catalog_schema.py fails if this file and the plan
-- ever disagree, so a change here is a change to the approved plan.
--
-- PRAGMA journal_mode is set at open time in connection.py, not here: it does not honour
-- busy_timeout.

-- BEGIN CORRECTED SCHEMA v2
PRAGMA foreign_keys = ON;

-- ── Collections ────────────────────────────────────────────────────────────
-- The closed fifteen (v1 ruling 1). The CHECK means a sixteenth collection needs
-- a schema migration, never an INSERT.
CREATE TABLE library_collection (
    collection_id  TEXT PRIMARY KEY CHECK (collection_id IN (
        'Constitution','Process','Operations','Compliance','Training','Reference',
        'Templates','Company','Customer','Broker','Location_Intelligence',
        'Route_Intelligence','Publisher_Parts','Security','Index')),
    name           TEXT    NOT NULL UNIQUE,
    purpose        TEXT,
    owner_role     TEXT,
    archive_policy TEXT,
    active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

INSERT INTO library_collection (collection_id, name) VALUES
    ('Constitution','Constitution'), ('Process','Process'), ('Operations','Operations'),
    ('Compliance','Compliance'), ('Training','Training'), ('Reference','Reference'),
    ('Templates','Templates'), ('Company','Company'), ('Customer','Customer'),
    ('Broker','Broker'), ('Location_Intelligence','Location_Intelligence'),
    ('Route_Intelligence','Route_Intelligence'), ('Publisher_Parts','Publisher_Parts'),
    ('Security','Security'), ('Index','Index');

-- ── Asset identity ─────────────────────────────────────────────────────────
-- One row per asset for its whole life. object_code is the COM code WITHOUT its
-- -v{MAJOR.MINOR} suffix; the versioned code is derived in library_current.
-- object_type is required and never inferred from collection (ruling 3).
CREATE TABLE library_object (
    library_object_id    TEXT    PRIMARY KEY CHECK (library_object_id GLOB 'libobj_?*'),
    object_code          TEXT    NOT NULL UNIQUE
                         CHECK (length(trim(object_code)) > 0 AND object_code NOT GLOB '*-v[0-9]*'),
    object_type          TEXT    NOT NULL CHECK (object_type IN (
        'CONSTITUTION_PACKAGE','AMENDMENT_CURRENT_RULE','ROLE_DOCTRINE','SOP_WORKFLOW',
        'OPERATIONAL_INSTRUCTION','COMPLIANCE_ASSET','CONTROLLED_COMPANY_FACT',
        'COMPANY_CREDENTIAL','CAPABILITY_ASSET','PAST_PERFORMANCE_REFERENCE',
        'RATE_SHEET_PRICING_TEMPLATE','PACKET','PACKET_COMPONENT','FORM_TEMPLATE',
        'TRAINING_ASSET_MANUAL','APPLIED_LESSON_PACKAGE','VALIDATED_INTELLIGENCE_SUMMARY',
        'LIBRARY_INDEX_MANIFEST')),
    collection_id        TEXT    NOT NULL REFERENCES library_collection (collection_id),
    title                TEXT    NOT NULL CHECK (length(trim(title)) > 0),
    slug                 TEXT    NOT NULL CHECK (length(trim(slug)) > 0),
    canonical_name       TEXT    NOT NULL CHECK (length(trim(canonical_name)) > 0),
    owner_role           TEXT    CHECK (owner_role IS NULL OR upper(trim(owner_role)) <> 'MANAGER'),
    access_level         TEXT,
    allowed_use          TEXT,
    current_only_default INTEGER NOT NULL DEFAULT 1 CHECK (current_only_default IN (0,1)),
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL,
    UNIQUE (collection_id, slug)
);

CREATE TRIGGER library_object_identity_is_immutable
BEFORE UPDATE ON library_object
WHEN NEW.library_object_id IS NOT OLD.library_object_id
  OR NEW.object_code       IS NOT OLD.object_code
  OR NEW.object_type       IS NOT OLD.object_type
  OR NEW.collection_id     IS NOT OLD.collection_id
  OR NEW.created_at        IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'library_object identity is immutable; a different identity is a different object');
END;

CREATE TRIGGER library_object_is_never_deleted
BEFORE DELETE ON library_object
BEGIN
    SELECT RAISE(ABORT, 'library objects are never deleted from the catalog');
END;

CREATE TABLE library_object_tag (
    library_object_id TEXT    NOT NULL REFERENCES library_object (library_object_id),
    tag               TEXT    NOT NULL CHECK (length(trim(tag)) > 0),
    position          INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (library_object_id, tag)
);

CREATE TABLE library_object_consumer (
    library_object_id TEXT NOT NULL REFERENCES library_object (library_object_id),
    consumer_role     TEXT NOT NULL
                      CHECK (length(trim(consumer_role)) > 0 AND upper(trim(consumer_role)) <> 'MANAGER'),
    PRIMARY KEY (library_object_id, consumer_role)
);

-- ── Candidate queue ────────────────────────────────────────────────────────
-- Sources per v1 ruling 3 and v2 ruling 5: Human, Intelligence, Publisher, and
-- Dispatch tied to a Mission Record or workflow event. Never Library.
-- SUBMITTED -> PENDING_REVIEW -> VALIDATED -> APPROVED (ruling 4).
CREATE TABLE library_candidate (
    candidate_id               TEXT PRIMARY KEY,
    submitted_by_role          TEXT NOT NULL
                               CHECK (submitted_by_role IN ('HUMAN','INTELLIGENCE','PUBLISHER','DISPATCH')),
    submitted_by_name          TEXT,
    mission_record_id          TEXT,
    workflow_event_id          TEXT,
    source_type                TEXT NOT NULL,
    -- Library's classification: a recommendation only.
    recommended_object_type    TEXT CHECK (recommended_object_type IS NULL OR recommended_object_type IN (
        'CONSTITUTION_PACKAGE','AMENDMENT_CURRENT_RULE','ROLE_DOCTRINE','SOP_WORKFLOW',
        'OPERATIONAL_INSTRUCTION','COMPLIANCE_ASSET','CONTROLLED_COMPANY_FACT',
        'COMPANY_CREDENTIAL','CAPABILITY_ASSET','PAST_PERFORMANCE_REFERENCE',
        'RATE_SHEET_PRICING_TEMPLATE','PACKET','PACKET_COMPONENT','FORM_TEMPLATE',
        'TRAINING_ASSET_MANUAL','APPLIED_LESSON_PACKAGE','VALIDATED_INTELLIGENCE_SUMMARY',
        'LIBRARY_INDEX_MANIFEST')),
    -- The type the asset will carry, confirmed by a human or the submitting source (ruling 3).
    proposed_object_type       TEXT CHECK (proposed_object_type IS NULL OR proposed_object_type IN (
        'CONSTITUTION_PACKAGE','AMENDMENT_CURRENT_RULE','ROLE_DOCTRINE','SOP_WORKFLOW',
        'OPERATIONAL_INSTRUCTION','COMPLIANCE_ASSET','CONTROLLED_COMPANY_FACT',
        'COMPANY_CREDENTIAL','CAPABILITY_ASSET','PAST_PERFORMANCE_REFERENCE',
        'RATE_SHEET_PRICING_TEMPLATE','PACKET','PACKET_COMPONENT','FORM_TEMPLATE',
        'TRAINING_ASSET_MANUAL','APPLIED_LESSON_PACKAGE','VALIDATED_INTELLIGENCE_SUMMARY',
        'LIBRARY_INDEX_MANIFEST')),
    object_type_confirmed_by   TEXT,
    object_type_confirmed_at   TEXT,
    proposed_collection_id     TEXT NOT NULL REFERENCES library_collection (collection_id),
    proposed_object_code       TEXT NOT NULL CHECK (length(trim(proposed_object_code)) > 0),
    proposed_title             TEXT NOT NULL,
    proposed_body_or_reference TEXT NOT NULL,
    source_finding_id          TEXT,
    status                     TEXT NOT NULL CHECK (status IN
        ('SUBMITTED','PENDING_REVIEW','VALIDATED','APPROVED','REJECTED','DEFERRED')),
    validation_result          TEXT NOT NULL DEFAULT 'NOT_RUN'
                               CHECK (validation_result IN ('PASSED','FAILED','NOT_RUN')),
    validated_at               TEXT,
    reviewed_by                TEXT,
    reviewed_at                TEXT,
    created_at                 TEXT NOT NULL,

    -- A human nomination carries a human name, and not a system's.
    CHECK (submitted_by_role <> 'HUMAN' OR (length(trim(ifnull(submitted_by_name,''))) > 0
           AND replace(replace(upper(trim(submitted_by_name)),' ','_'),'-','_') NOT IN
               ('INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER'))),
    -- Dispatch nominates only from a real Mission Record or workflow event.
    CHECK (submitted_by_role <> 'DISPATCH' OR mission_record_id IS NOT NULL OR workflow_event_id IS NOT NULL),
    -- A decision has a name on it; an undecided candidate does not.
    CHECK ((status IN ('APPROVED','REJECTED','DEFERRED')) = (reviewed_by IS NOT NULL)),
    CHECK (reviewed_by IS NULL OR replace(replace(upper(trim(reviewed_by)),' ','_'),'-','_') NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER')),
    -- Object type confirmation: a real human, or the worker that submitted the
    -- candidate. Never Library, never another system (rulings 3 and 5).
    CHECK ((object_type_confirmed_by IS NULL) = (object_type_confirmed_at IS NULL)),
    CHECK (object_type_confirmed_by IS NULL OR proposed_object_type IS NOT NULL),
    CHECK (object_type_confirmed_by IS NULL
        OR (submitted_by_role <> 'HUMAN'
            AND replace(replace(upper(trim(object_type_confirmed_by)),' ','_'),'-','_') = submitted_by_role)
        OR replace(replace(upper(trim(object_type_confirmed_by)),' ','_'),'-','_') NOT IN
           ('HUMAN','INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER')),
    -- Validated and approved candidates passed validation and carry a confirmed type.
    CHECK (status NOT IN ('VALIDATED','APPROVED') OR
           (validation_result = 'PASSED' AND object_type_confirmed_by IS NOT NULL))
);

CREATE INDEX library_candidate_queue ON library_candidate (status, created_at);

CREATE TRIGGER library_candidate_enters_submitted
BEFORE INSERT ON library_candidate
WHEN NEW.status <> 'SUBMITTED'
BEGIN
    SELECT RAISE(ABORT, 'a candidate enters as SUBMITTED');
END;

CREATE TRIGGER library_candidate_moves_legally
BEFORE UPDATE OF status ON library_candidate
WHEN NEW.status IS NOT OLD.status AND NOT (
       (OLD.status = 'SUBMITTED'      AND NEW.status = 'PENDING_REVIEW')
    OR (OLD.status = 'PENDING_REVIEW' AND NEW.status IN ('VALIDATED','REJECTED','DEFERRED'))
    OR (OLD.status = 'VALIDATED'      AND NEW.status IN ('APPROVED','REJECTED','DEFERRED'))
    OR (OLD.status = 'DEFERRED'       AND NEW.status = 'PENDING_REVIEW'))
BEGIN
    SELECT RAISE(ABORT, 'illegal candidate status transition');
END;

CREATE TRIGGER library_candidate_type_change_needs_reconfirmation
BEFORE UPDATE OF proposed_object_type ON library_candidate
WHEN NEW.proposed_object_type IS NOT OLD.proposed_object_type
 AND OLD.object_type_confirmed_at IS NOT NULL
 AND NEW.object_type_confirmed_at IS OLD.object_type_confirmed_at
BEGIN
    SELECT RAISE(ABORT, 'changing a confirmed object type needs a new confirmation');
END;

-- ── Approval records ───────────────────────────────────────────────────────
-- Every approval, including a human placing a document. For HUMAN_PLACED the
-- record is the approval written down, not a second gate (ruling 4).
-- capture_channel records how the approval arrived -- e.g. JOE -- and is never
-- the approver (ruling 6).
CREATE TABLE approval_record (
    approval_record_id TEXT PRIMARY KEY,
    library_object_id  TEXT REFERENCES library_object (library_object_id),
    version_id         TEXT REFERENCES library_version (version_id) DEFERRABLE INITIALLY DEFERRED,
    candidate_id       TEXT REFERENCES library_candidate (candidate_id),
    approver           TEXT NOT NULL CHECK (length(trim(approver)) > 0),
    approval_status    TEXT NOT NULL CHECK (approval_status IN ('APPROVED','REJECTED','DEFERRED')),
    approval_basis     TEXT NOT NULL CHECK (approval_basis IN ('HUMAN_PLACED','CANDIDATE_REVIEW')),
    authority_basis    TEXT,
    capture_channel    TEXT,
    capture_ref        TEXT,
    approved_at        TEXT NOT NULL,
    notes              TEXT NOT NULL DEFAULT '',

    -- No system identity manufactures a human approval.
    CHECK (replace(replace(upper(trim(approver)),' ','_'),'-','_') NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER')),
    CHECK (capture_ref IS NULL OR capture_channel IS NOT NULL),
    CHECK (approval_basis = 'CANDIDATE_REVIEW' OR (candidate_id IS NULL AND approval_status = 'APPROVED')),
    CHECK (approval_basis = 'HUMAN_PLACED' OR candidate_id IS NOT NULL),
    CHECK ((approval_status = 'APPROVED' AND library_object_id IS NOT NULL AND version_id IS NOT NULL)
        OR (approval_status <> 'APPROVED' AND version_id IS NULL))
);

CREATE UNIQUE INDEX approval_record_one_per_version
    ON approval_record (version_id) WHERE version_id IS NOT NULL;

-- A candidate is approved only once validated, and only into an object carrying
-- the confirmed type and the proposed collection.
CREATE TRIGGER approval_record_candidate_must_be_validated
BEFORE INSERT ON approval_record
WHEN NEW.approval_basis = 'CANDIDATE_REVIEW' AND NEW.approval_status = 'APPROVED'
 AND NOT EXISTS (SELECT 1 FROM library_candidate c
                 JOIN library_object o ON o.library_object_id = NEW.library_object_id
                 WHERE c.candidate_id = NEW.candidate_id
                   AND c.status = 'VALIDATED'
                   AND o.object_type = c.proposed_object_type
                   AND o.collection_id = c.proposed_collection_id)
BEGIN
    SELECT RAISE(ABORT, 'a candidate is approved only after validation, into an object of its confirmed type and proposed collection');
END;

CREATE TRIGGER approval_record_is_append_only_update
BEFORE UPDATE ON approval_record
BEGIN
    SELECT RAISE(ABORT, 'approval records are never edited');
END;

CREATE TRIGGER approval_record_is_append_only_delete
BEFORE DELETE ON approval_record
BEGIN
    SELECT RAISE(ABORT, 'approval records are never deleted');
END;

CREATE TRIGGER library_candidate_decision_is_recorded
BEFORE UPDATE OF status ON library_candidate
WHEN NEW.status IN ('APPROVED','REJECTED','DEFERRED') AND NEW.status IS NOT OLD.status
 AND NOT EXISTS (SELECT 1 FROM approval_record a
                 WHERE a.candidate_id = NEW.candidate_id
                   AND a.approval_status = NEW.status
                   AND a.approver = NEW.reviewed_by)
BEGIN
    SELECT RAISE(ABORT, 'a candidate decision needs an approval record by the same reviewer');
END;

-- ── Versions ───────────────────────────────────────────────────────────────
CREATE TABLE library_version (
    version_id                TEXT    PRIMARY KEY CHECK (version_id GLOB 'libver_?*'),
    library_object_id         TEXT    NOT NULL REFERENCES library_object (library_object_id),
    version_major             INTEGER NOT NULL CHECK (version_major >= 1),
    version_minor             INTEGER NOT NULL CHECK (version_minor >= 0),
    lifecycle_state           TEXT    NOT NULL CHECK (lifecycle_state IN
        ('CURRENT','ACTIVE_USE','REVIEW_DUE','SUPERSEDED','ARCHIVED_VERSION_RECORD','RETENTION_REVIEW')),
    is_current                INTEGER GENERATED ALWAYS AS
        (lifecycle_state IN ('CURRENT','ACTIVE_USE','REVIEW_DUE')) STORED,
    title                     TEXT    NOT NULL CHECK (length(trim(title)) > 0),

    -- Content: inline, or a file on the shelf. content_uri is always set.
    content_uri               TEXT    NOT NULL CHECK (length(trim(content_uri)) > 0),
    body                      TEXT,
    relative_path             TEXT    COLLATE NOCASE,
    content_sha256            TEXT,
    size_bytes                INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
    observed_at               TEXT,

    effective_date            TEXT,
    review_cycle              TEXT,
    review_due_date           TEXT,
    supersedes_version_id     TEXT    REFERENCES library_version (version_id),
    approval_record_id        TEXT    NOT NULL REFERENCES approval_record (approval_record_id),

    created_from_workspace_id TEXT,
    created_from_archive_id   TEXT,
    source_confidence         TEXT,
    no_fabrication_check      TEXT    NOT NULL DEFAULT 'NOT_RUN'
                              CHECK (no_fabrication_check IN ('PASSED','FAILED','NOT_RUN')),
    validation_gate           TEXT,
    validation_result         TEXT    NOT NULL DEFAULT 'NOT_RUN'
                              CHECK (validation_result IN ('PASSED','FAILED','NOT_RUN')),
    drift_check_result        TEXT    NOT NULL DEFAULT 'NOT_RUN'
                              CHECK (drift_check_result IN ('PASSED','FAILED','NOT_RUN')),
    quality_check_result      TEXT    NOT NULL DEFAULT 'NOT_RUN'
                              CHECK (quality_check_result IN ('PASSED','FAILED','NOT_RUN')),
    conflict_notice_id        TEXT    REFERENCES library_notice (notice_id),
    retention_class           TEXT,
    created_at                TEXT    NOT NULL,

    UNIQUE (library_object_id, version_major, version_minor),
    -- Shelf binding is all or nothing.
    CHECK ((relative_path IS NULL AND content_sha256 IS NULL AND size_bytes IS NULL AND observed_at IS NULL)
        OR (relative_path IS NOT NULL AND content_sha256 IS NOT NULL AND size_bytes IS NOT NULL AND observed_at IS NOT NULL)),
    CHECK (content_sha256 IS NULL OR (length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*')),
    -- Relative, POSIX, inside the shelf.
    CHECK (relative_path IS NULL OR (
           relative_path NOT GLOB '*\*' AND relative_path NOT GLOB '/*' AND relative_path NOT GLOB '[A-Za-z]:*'
       AND relative_path <> '..' AND relative_path NOT GLOB '../*'
       AND relative_path NOT GLOB '*/../*' AND relative_path NOT GLOB '*/..')),
    CHECK (body IS NULL OR relative_path IS NULL),
    -- Nothing that failed a check stands as an approved version.
    CHECK (validation_result <> 'FAILED' AND no_fabrication_check <> 'FAILED' AND quality_check_result <> 'FAILED')
);

-- Exactly one current version per asset.
CREATE UNIQUE INDEX library_version_one_current
    ON library_version (library_object_id) WHERE is_current = 1;

-- One current version per shelf file, case-insensitively as Windows resolves paths.
CREATE UNIQUE INDEX library_version_one_current_per_file
    ON library_version (relative_path COLLATE NOCASE)
    WHERE is_current = 1 AND relative_path IS NOT NULL;

-- A version is superseded by at most one successor.
CREATE UNIQUE INDEX library_version_one_successor
    ON library_version (supersedes_version_id) WHERE supersedes_version_id IS NOT NULL;

CREATE INDEX library_version_by_object ON library_version (library_object_id, version_major, version_minor);

CREATE TRIGGER library_version_needs_its_own_approval
BEFORE INSERT ON library_version
WHEN NOT EXISTS (SELECT 1 FROM approval_record a
                 WHERE a.approval_record_id = NEW.approval_record_id
                   AND a.approval_status    = 'APPROVED'
                   AND a.version_id         = NEW.version_id
                   AND a.library_object_id  = NEW.library_object_id)
BEGIN
    SELECT RAISE(ABORT, 'a version needs an APPROVED approval record that names this version');
END;

CREATE TRIGGER library_version_enters_current
BEFORE INSERT ON library_version
WHEN NEW.lifecycle_state <> 'CURRENT'
BEGIN
    SELECT RAISE(ABORT, 'a version enters the catalog as CURRENT');
END;

CREATE TRIGGER library_version_moves_forward
BEFORE INSERT ON library_version
WHEN EXISTS (SELECT 1 FROM library_version v
             WHERE v.library_object_id = NEW.library_object_id
               AND (v.version_major > NEW.version_major
                    OR (v.version_major = NEW.version_major AND v.version_minor >= NEW.version_minor)))
BEGIN
    SELECT RAISE(ABORT, 'a new version must be later than every existing version of the object');
END;

-- Transactional supersession: a later version must name the version it replaces,
-- and that version must already have been moved to SUPERSEDED in the same
-- transaction. Out of order, the one-current index refuses the insert.
CREATE TRIGGER library_version_supersedes_correctly
BEFORE INSERT ON library_version
WHEN (EXISTS (SELECT 1 FROM library_version v WHERE v.library_object_id = NEW.library_object_id)
      AND (NEW.supersedes_version_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM library_version v
                          WHERE v.version_id = NEW.supersedes_version_id
                            AND v.library_object_id = NEW.library_object_id
                            AND v.lifecycle_state = 'SUPERSEDED')))
  OR (NOT EXISTS (SELECT 1 FROM library_version v WHERE v.library_object_id = NEW.library_object_id)
      AND NEW.supersedes_version_id IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'a later version must supersede a SUPERSEDED version of the same object; a first version supersedes nothing');
END;

CREATE TRIGGER library_version_content_is_immutable
BEFORE UPDATE ON library_version
WHEN NEW.version_id                IS NOT OLD.version_id
  OR NEW.library_object_id         IS NOT OLD.library_object_id
  OR NEW.version_major             IS NOT OLD.version_major
  OR NEW.version_minor             IS NOT OLD.version_minor
  OR NEW.title                     IS NOT OLD.title
  OR NEW.content_uri               IS NOT OLD.content_uri
  OR NEW.body                      IS NOT OLD.body
  OR NEW.relative_path             IS NOT OLD.relative_path
  OR NEW.content_sha256            IS NOT OLD.content_sha256
  OR NEW.size_bytes                IS NOT OLD.size_bytes
  OR NEW.effective_date            IS NOT OLD.effective_date
  OR NEW.supersedes_version_id     IS NOT OLD.supersedes_version_id
  OR NEW.approval_record_id        IS NOT OLD.approval_record_id
  OR NEW.created_from_workspace_id IS NOT OLD.created_from_workspace_id
  OR NEW.created_from_archive_id   IS NOT OLD.created_from_archive_id
  OR NEW.source_confidence         IS NOT OLD.source_confidence
  OR NEW.no_fabrication_check      IS NOT OLD.no_fabrication_check
  OR NEW.validation_gate           IS NOT OLD.validation_gate
  OR NEW.validation_result         IS NOT OLD.validation_result
  OR NEW.quality_check_result      IS NOT OLD.quality_check_result
  OR NEW.created_at                IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'approved version content is immutable; a change is a new version');
END;

CREATE TRIGGER library_version_lifecycle_moves_legally
BEFORE UPDATE OF lifecycle_state ON library_version
WHEN NEW.lifecycle_state IS NOT OLD.lifecycle_state AND NOT (
       (OLD.lifecycle_state IN ('CURRENT','ACTIVE_USE','REVIEW_DUE')
        AND NEW.lifecycle_state IN ('CURRENT','ACTIVE_USE','REVIEW_DUE','SUPERSEDED'))
    OR (OLD.lifecycle_state = 'SUPERSEDED'              AND NEW.lifecycle_state = 'ARCHIVED_VERSION_RECORD')
    OR (OLD.lifecycle_state = 'ARCHIVED_VERSION_RECORD' AND NEW.lifecycle_state = 'RETENTION_REVIEW'))
BEGIN
    SELECT RAISE(ABORT, 'illegal lifecycle transition');
END;

CREATE TRIGGER library_version_archived_needs_archive_link
BEFORE UPDATE OF lifecycle_state ON library_version
WHEN NEW.lifecycle_state = 'ARCHIVED_VERSION_RECORD' AND OLD.lifecycle_state <> 'ARCHIVED_VERSION_RECORD'
 AND NOT EXISTS (SELECT 1 FROM archive_link l
                 WHERE l.version_id = NEW.version_id AND l.relationship_type = 'SUPERSEDED_VERSION')
BEGIN
    SELECT RAISE(ABORT, 'a version becomes an Archive version record only with a SUPERSEDED_VERSION Archive link');
END;

CREATE TRIGGER library_version_retention_review_needs_queue
BEFORE UPDATE OF lifecycle_state ON library_version
WHEN NEW.lifecycle_state = 'RETENTION_REVIEW' AND OLD.lifecycle_state <> 'RETENTION_REVIEW'
 AND NOT EXISTS (SELECT 1 FROM archive_review_queue q WHERE q.version_id = NEW.version_id)
BEGIN
    SELECT RAISE(ABORT, 'a version enters RETENTION_REVIEW only through the Archive Review Queue');
END;

CREATE TRIGGER library_version_is_never_deleted
BEFORE DELETE ON library_version
BEGIN
    SELECT RAISE(ABORT, 'versions are never deleted from the catalog');
END;

-- ── Notices ────────────────────────────────────────────────────────────────
-- What Library may do instead of nominating (ruling 5): record a missing field,
-- a blocked piece of work, a conflict, or an expired, changed, missing or
-- uncatalogued asset, with a recommended type and action. The asset itself
-- stays uncatalogued or incomplete (ruling 3). Library raises a notice and does
-- not settle it; a human or an authorised source does.
CREATE TABLE library_notice (
    notice_id               TEXT    PRIMARY KEY,
    notice_type             TEXT    NOT NULL CHECK (notice_type IN
        ('MISSING_FIELD','BLOCKED_WORK','CONFLICT','EXPIRED','CHANGED','MISSING','UNCATALOGUED')),
    relative_path           TEXT    COLLATE NOCASE,
    candidate_id            TEXT    REFERENCES library_candidate (candidate_id),
    library_object_id       TEXT    REFERENCES library_object (library_object_id),
    version_id              TEXT    REFERENCES library_version (version_id),
    scan_id                 INTEGER REFERENCES catalog_scan (scan_id),
    missing_field           TEXT,
    recommended_object_type TEXT    CHECK (recommended_object_type IS NULL OR recommended_object_type IN (
        'CONSTITUTION_PACKAGE','AMENDMENT_CURRENT_RULE','ROLE_DOCTRINE','SOP_WORKFLOW',
        'OPERATIONAL_INSTRUCTION','COMPLIANCE_ASSET','CONTROLLED_COMPANY_FACT',
        'COMPANY_CREDENTIAL','CAPABILITY_ASSET','PAST_PERFORMANCE_REFERENCE',
        'RATE_SHEET_PRICING_TEMPLATE','PACKET','PACKET_COMPONENT','FORM_TEMPLATE',
        'TRAINING_ASSET_MANUAL','APPLIED_LESSON_PACKAGE','VALIDATED_INTELLIGENCE_SUMMARY',
        'LIBRARY_INDEX_MANIFEST')),
    recommended_action      TEXT    NOT NULL DEFAULT '',
    detail                  TEXT    NOT NULL DEFAULT '',
    raised_by               TEXT    NOT NULL DEFAULT 'LIBRARY',
    raised_at               TEXT    NOT NULL,
    status                  TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','RESOLVED')),
    resolved_by             TEXT,
    resolved_at             TEXT,
    resolution              TEXT,
    CHECK (relative_path IS NOT NULL OR candidate_id IS NOT NULL
        OR library_object_id IS NOT NULL OR version_id IS NOT NULL),
    CHECK (notice_type <> 'MISSING_FIELD' OR missing_field IS NOT NULL),
    CHECK ((status = 'OPEN' AND resolved_by IS NULL AND resolved_at IS NULL AND resolution IS NULL)
        OR (status = 'RESOLVED' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL AND resolution IS NOT NULL)),
    -- Settled by a human or an authorised source: Intelligence, Publisher, or a Dispatch workflow.
    CHECK (resolved_by IS NULL OR replace(replace(upper(trim(resolved_by)),' ','_'),'-','_') NOT IN
           ('LIBRARY','JOE','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER'))
);

CREATE INDEX library_notice_open ON library_notice (status, notice_type, raised_at);

CREATE TRIGGER library_notice_resolution_is_final
BEFORE UPDATE ON library_notice WHEN OLD.status = 'RESOLVED'
BEGIN
    SELECT RAISE(ABORT, 'a resolved notice is a record and is not edited');
END;

CREATE TRIGGER library_notice_is_never_deleted
BEFORE DELETE ON library_notice
BEGIN
    SELECT RAISE(ABORT, 'notices are never deleted');
END;

-- ── Metadata ───────────────────────────────────────────────────────────────
-- COM §4 per-type metadata additions (issuing_authority, expiration_date, ...).
-- version_id NULL means the value belongs to the object across versions.
CREATE TABLE library_metadata (
    metadata_id       TEXT PRIMARY KEY,
    library_object_id TEXT NOT NULL REFERENCES library_object (library_object_id),
    version_id        TEXT REFERENCES library_version (version_id),
    key               TEXT NOT NULL CHECK (length(trim(key)) > 0),
    value             TEXT NOT NULL,
    value_type        TEXT NOT NULL DEFAULT 'TEXT'
                      CHECK (value_type IN ('TEXT','INTEGER','DECIMAL','BOOLEAN','DATE','JSON'))
);

CREATE UNIQUE INDEX library_metadata_one_value
    ON library_metadata (library_object_id, ifnull(version_id, ''), key);

CREATE TRIGGER library_metadata_version_belongs
BEFORE INSERT ON library_metadata
WHEN NEW.version_id IS NOT NULL AND NOT EXISTS (
     SELECT 1 FROM library_version v
     WHERE v.version_id = NEW.version_id AND v.library_object_id = NEW.library_object_id)
BEGIN
    SELECT RAISE(ABORT, 'metadata version must belong to the same object');
END;

-- ── Source and provenance ──────────────────────────────────────────────────
CREATE TABLE source_ref (
    source_ref_id TEXT PRIMARY KEY,
    version_id    TEXT REFERENCES library_version (version_id),
    candidate_id  TEXT REFERENCES library_candidate (candidate_id),
    ref_kind      TEXT NOT NULL CHECK (ref_kind IN (
        'LIBRARY_VERSION','ARCHIVE_RECORD','WORKSPACE','SHELF_FILE',
        'EXTERNAL_DOCUMENT','INTELLIGENCE_FINDING','MISSION_RECORD','WORKFLOW_EVENT')),
    reference     TEXT NOT NULL CHECK (length(trim(reference)) > 0),
    note          TEXT NOT NULL DEFAULT '',
    CHECK ((version_id IS NULL) <> (candidate_id IS NULL))
);

CREATE TRIGGER source_ref_of_a_version_is_fixed_update
BEFORE UPDATE ON source_ref WHEN OLD.version_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'the sources of an approved version are part of its record');
END;

CREATE TRIGGER source_ref_of_a_version_is_fixed_delete
BEFORE DELETE ON source_ref WHEN OLD.version_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'the sources of an approved version are part of its record');
END;

-- ── Archive references ─────────────────────────────────────────────────────
-- archive_record_id is an identifier in Archive, a separate store. It is not a
-- foreign key because the catalog cannot see Archive.
CREATE TABLE archive_link (
    archive_link_id    TEXT PRIMARY KEY,
    library_object_id  TEXT NOT NULL REFERENCES library_object (library_object_id),
    version_id         TEXT REFERENCES library_version (version_id),
    approval_record_id TEXT REFERENCES approval_record (approval_record_id),
    archive_record_id  TEXT NOT NULL CHECK (length(trim(archive_record_id)) > 0),
    relationship_type  TEXT NOT NULL CHECK (relationship_type IN
        ('ARCHIVE_RECORD','SUPERSEDED_VERSION','APPROVAL_RECORD','SOURCE_EVIDENCE')),
    description        TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    CHECK (relationship_type <> 'SUPERSEDED_VERSION' OR version_id IS NOT NULL),
    CHECK (relationship_type <> 'APPROVAL_RECORD' OR approval_record_id IS NOT NULL)
);

CREATE TRIGGER archive_link_version_belongs
BEFORE INSERT ON archive_link
WHEN NEW.version_id IS NOT NULL AND NOT EXISTS (
     SELECT 1 FROM library_version v
     WHERE v.version_id = NEW.version_id AND v.library_object_id = NEW.library_object_id)
BEGIN
    SELECT RAISE(ABORT, 'archive link version must belong to the same object');
END;

-- ARCHIVE_REVIEW_POLICY.md §2-4: current plus three previous retained; older
-- versions queue for Mike's Keep/Delete decision. Nothing here deletes anything.
CREATE TABLE archive_review_queue (
    version_id  TEXT PRIMARY KEY REFERENCES library_version (version_id),
    queued_at   TEXT NOT NULL,
    disposition TEXT NOT NULL DEFAULT 'PENDING' CHECK (disposition IN ('PENDING','KEEP','DELETE')),
    decided_by  TEXT,
    decided_at  TEXT,
    CHECK ((disposition = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL)
        OR (disposition <> 'PENDING' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK (decided_by IS NULL OR replace(replace(upper(trim(decided_by)),' ','_'),'-','_') NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','JOE','DISPATCH','SYSTEM','AUTOMATION','COMI','EMAIL_HELPER'))
);

CREATE TRIGGER archive_review_queue_takes_no_current_version
BEFORE INSERT ON archive_review_queue
WHEN EXISTS (SELECT 1 FROM library_version v WHERE v.version_id = NEW.version_id AND v.is_current = 1)
BEGIN
    SELECT RAISE(ABORT, 'a current version is not queued for archive review');
END;

CREATE TRIGGER archive_review_decision_is_final
BEFORE UPDATE ON archive_review_queue WHEN OLD.disposition <> 'PENDING'
BEGIN
    SELECT RAISE(ABORT, 'an archive review decision is final once made');
END;

-- ── Object relationships ───────────────────────────────────────────────────
CREATE TABLE object_relationship (
    relationship_id   TEXT    PRIMARY KEY,
    from_object_id    TEXT    NOT NULL REFERENCES library_object (library_object_id),
    to_object_id      TEXT    NOT NULL REFERENCES library_object (library_object_id),
    relationship_type TEXT    NOT NULL CHECK (relationship_type IN
        ('RELATED','DEPENDS_ON','USED_BY','REPLACES','DERIVED_FROM')),
    active            INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    created_at        TEXT    NOT NULL,
    CHECK (from_object_id <> to_object_id),
    UNIQUE (from_object_id, to_object_id, relationship_type)
);

-- ── Retrieval events ───────────────────────────────────────────────────────
CREATE TABLE retrieval_event (
    retrieval_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    consumer_role         TEXT    NOT NULL
                          CHECK (length(trim(consumer_role)) > 0 AND upper(trim(consumer_role)) <> 'MANAGER'),
    requested_object_code TEXT    NOT NULL,
    library_object_id     TEXT    REFERENCES library_object (library_object_id),
    version_id            TEXT    REFERENCES library_version (version_id),
    purpose               TEXT    NOT NULL DEFAULT '',
    current_only          INTEGER NOT NULL DEFAULT 1 CHECK (current_only IN (0,1)),
    outcome               TEXT    NOT NULL CHECK (outcome IN
        ('RETURNED','MISSING','ARCHIVE_REFERENCE_ONLY','BLOCKED_REVIEW_DUE')),
    retrieved_at          TEXT    NOT NULL,
    CHECK (outcome <> 'RETURNED' OR (library_object_id IS NOT NULL AND version_id IS NOT NULL)),
    CHECK (outcome <> 'MISSING' OR version_id IS NULL)
);

-- COM §7 retrieval check: a current-only retrieval returns a current version that
-- is cleared for use. REVIEW_DUE is current but blocked (COM §8 expired credential).
CREATE TRIGGER retrieval_event_current_only_returns_current
BEFORE INSERT ON retrieval_event
WHEN NEW.outcome = 'RETURNED' AND NEW.current_only = 1 AND NOT EXISTS (
     SELECT 1 FROM library_version v
     WHERE v.version_id = NEW.version_id AND v.library_object_id = NEW.library_object_id
       AND v.is_current = 1 AND v.lifecycle_state <> 'REVIEW_DUE')
BEGIN
    SELECT RAISE(ABORT, 'a current-only retrieval may return only a current, not review-due, version');
END;

CREATE TRIGGER retrieval_event_is_append_only_update
BEFORE UPDATE ON retrieval_event
BEGIN
    SELECT RAISE(ABORT, 'retrieval events are a record and are never edited');
END;

CREATE TRIGGER retrieval_event_is_append_only_delete
BEFORE DELETE ON retrieval_event
BEGIN
    SELECT RAISE(ABORT, 'retrieval events are a record and are never deleted');
END;

-- ── Recipes ────────────────────────────────────────────────────────────────
-- v1 ruling 6: every source field of publisher_recipes.json has a column or a
-- requirement kind; placeholders say so and carry nothing.
CREATE TABLE publisher_recipe (
    recipe_id             TEXT    PRIMARY KEY,
    recipe_code           TEXT    NOT NULL UNIQUE,
    recipe_type           TEXT    NOT NULL CHECK (recipe_type IN (
        'BROKER_ONBOARDING_PACKET','GOVERNMENT_PROPOSAL_PACKET','VISIBILITY_STATUS_PACKET',
        'POD_PACKAGE','REVIEW_PACKAGE')),
    version               INTEGER NOT NULL CHECK (version >= 1),
    status                TEXT    NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED')),
    is_placeholder        INTEGER NOT NULL CHECK (is_placeholder IN (0,1)),
    recipe_name           TEXT,
    source_key            TEXT,
    human_review_required INTEGER CHECK (human_review_required IN (0,1)),
    source_path           TEXT,
    source_sha256         TEXT,
    loaded_at             TEXT    NOT NULL,
    CHECK ((is_placeholder = 1 AND recipe_name IS NULL AND source_key IS NULL
            AND human_review_required IS NULL AND source_path IS NULL AND source_sha256 IS NULL)
        OR (is_placeholder = 0 AND recipe_name IS NOT NULL AND source_key IS NOT NULL
            AND human_review_required IS NOT NULL AND source_path IS NOT NULL AND source_sha256 IS NOT NULL))
);

CREATE UNIQUE INDEX publisher_recipe_one_current
    ON publisher_recipe (recipe_type) WHERE status = 'CURRENT';

CREATE TABLE recipe_requirement (
    recipe_id TEXT    NOT NULL REFERENCES publisher_recipe (recipe_id),
    kind      TEXT    NOT NULL CHECK (kind IN
        ('COMPANY_ITEM','PUBLISHER_ITEM','HUMAN_ITEM','OUTPUT','INTELLIGENCE_REQUIREMENT')),
    value     TEXT    NOT NULL CHECK (length(trim(value)) > 0),
    position  INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (recipe_id, kind, value),
    UNIQUE (recipe_id, kind, position)
);

CREATE TRIGGER recipe_requirement_not_on_placeholder
BEFORE INSERT ON recipe_requirement
WHEN (SELECT is_placeholder FROM publisher_recipe WHERE recipe_id = NEW.recipe_id) = 1
BEGIN
    SELECT RAISE(ABORT, 'a placeholder recipe carries no requirements');
END;

-- ── Scans and findings ─────────────────────────────────────────────────────
-- A dry run writes no rows at all, so every row here is a recorded scan.
CREATE TABLE catalog_scan (
    scan_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at         TEXT    NOT NULL,
    finished_at        TEXT,
    memory_root        TEXT    NOT NULL,
    files_seen         INTEGER NOT NULL DEFAULT 0 CHECK (files_seen >= 0),
    folders_seen       INTEGER NOT NULL DEFAULT 0 CHECK (folders_seen >= 0),
    mapping_version_id TEXT    REFERENCES library_version (version_id)
);

CREATE TRIGGER catalog_scan_is_closed_once_finished
BEFORE UPDATE ON catalog_scan WHEN OLD.finished_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'a finished scan is a record and is not edited');
END;

CREATE TABLE catalog_finding (
    finding_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             INTEGER NOT NULL REFERENCES catalog_scan (scan_id),
    relative_path       TEXT    NOT NULL,
    finding             TEXT    NOT NULL CHECK (finding IN
        ('UNCATALOGUED','CHANGED','MISSING','UNMAPPED_FOLDER','PLACEMENT_CONFLICT')),
    version_id          TEXT    REFERENCES library_version (version_id),
    observed_sha256     TEXT,
    observed_size_bytes INTEGER,
    detail              TEXT    NOT NULL DEFAULT '',
    UNIQUE (scan_id, relative_path, finding),
    CHECK (finding NOT IN ('CHANGED','MISSING') OR version_id IS NOT NULL)
);

CREATE TRIGGER catalog_finding_only_on_open_scan
BEFORE INSERT ON catalog_finding
WHEN (SELECT finished_at FROM catalog_scan WHERE scan_id = NEW.scan_id) IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'findings are added only while their scan is open');
END;

CREATE TRIGGER catalog_finding_is_append_only_update
BEFORE UPDATE ON catalog_finding
BEGIN
    SELECT RAISE(ABORT, 'findings are a record and are never edited');
END;

CREATE TRIGGER catalog_finding_is_append_only_delete
BEFORE DELETE ON catalog_finding
BEGIN
    SELECT RAISE(ABORT, 'findings are a record and are never deleted');
END;

-- ── Views: derived, never stored ───────────────────────────────────────────
CREATE VIEW library_current AS
SELECT o.library_object_id, o.object_code, o.object_type, o.collection_id, o.title AS object_title,
       v.version_id AS current_version_id, v.version_major, v.version_minor,
       o.object_code || '-v' || v.version_major || '.' || v.version_minor AS versioned_code,
       v.lifecycle_state, v.title, v.content_uri, v.body, v.relative_path, v.content_sha256,
       v.size_bytes, v.observed_at, v.review_due_date,
       a.approver, a.approved_at, a.approval_basis, a.approval_status, a.capture_channel
FROM library_object o
JOIN library_version v ON v.library_object_id = o.library_object_id AND v.is_current = 1
JOIN approval_record a ON a.approval_record_id = v.approval_record_id;

CREATE VIEW library_version_lineage AS
SELECT v.version_id, v.library_object_id, v.version_major, v.version_minor, v.lifecycle_state,
       v.supersedes_version_id, successor.version_id AS superseded_by_version_id
FROM library_version v
LEFT JOIN library_version successor ON successor.supersedes_version_id = v.version_id;

CREATE VIEW library_object_without_version AS
SELECT o.* FROM library_object o
WHERE NOT EXISTS (SELECT 1 FROM library_version v WHERE v.library_object_id = o.library_object_id);

CREATE VIEW catalog_scan_summary AS
SELECT s.scan_id, s.started_at, s.finished_at, s.memory_root, s.files_seen, s.folders_seen,
       coalesce(sum(f.finding = 'UNCATALOGUED'), 0)       AS uncatalogued,
       coalesce(sum(f.finding = 'CHANGED'), 0)            AS changed,
       coalesce(sum(f.finding = 'MISSING'), 0)            AS missing,
       coalesce(sum(f.finding = 'UNMAPPED_FOLDER'), 0)    AS unmapped_folders,
       coalesce(sum(f.finding = 'PLACEMENT_CONFLICT'), 0) AS placement_conflicts
FROM catalog_scan s LEFT JOIN catalog_finding f ON f.scan_id = s.scan_id
GROUP BY s.scan_id;

CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL,
    description TEXT NOT NULL
);
-- END CORRECTED SCHEMA v2
