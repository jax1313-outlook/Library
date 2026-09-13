# LIBRARY_IMPLEMENTATION_PLAN_v2 — corrected persistent-catalog schema

**Program:** Dispatch
**Authority:** Mike Zachary — final authority
**Status:** Schema package with owner rulings applied. **Nothing in this document has been
built.** The corrected schema is not implemented; the next review must confirm the five items in
§6.1 first.
**Date:** 2026-09-13
**Supersedes:** `LIBRARY_IMPLEMENTATION_PLAN_v1.md` §3 (schema) and §10 (sequence). v1 is kept
unchanged as the record, with its §15 (Core Object Model reconciliation) and §16 (first owner
ruling).

**Design authority:** the Library Department Core Object Model (COM), `D:\Library`.
**Implementation authority for collections:** `src/dispatch_library/taxonomy.py` — fifteen
collections including Security (v1 §16, ruling 1).
**Owner rulings applied:** v1 §16 rulings 1–7, and the v2 schema decisions in §0 below.

This is not a redesign. Every table traces to a COM field, a COM §9 table, an owner ruling, or a
v1 mechanism that already exists; §3 shows which, row by row. Where the COM left something open,
the choice made is named as a choice.

---

## 0. Owner ruling — v2 schema decisions, Mike Zachary, 2026-09-13

Given by Mike Zachary in the local session after reviewing the first draft of this document.
Recorded as he stated it; nothing below extends his approval beyond what he stated.

| # | Subject | Ruling |
|---|---|---|
| 1 | **Authoritative Library** | The separate **Library repository is the authoritative Library Department.** `D:\Memory` is the physical shelf. Library owns the catalog, object identity, versions, approval records, current resolution, recipes, retrieval, candidate queue and Archive references. Dispatch and Portal consume or display Library information through bounded interfaces and do not own a second authoritative Library. Dispatch's `portal/models/library.py` JSON implementation is inventoried as a **legacy or temporary projection** — not deleted, removed, migrated or replaced during this schema mission; its callers are identified and compatibility is preserved until the authoritative Library can safely replace its function (§4.11). |
| 2 | **Shared contract** | Additive changes approved for MAJOR.MINOR versioning; Human as a candidate source; Dispatch as a candidate source only when tied to a real Mission Record or workflow event; Dispatch and other system identities as prohibited human approvers. Preserve compatibility wherever possible; do not silently replace shared fields used by Intelligence, Publisher, Joe or Dispatch. |
| 3 | **Object type** | `object_type` is **required** and is **not inferred from collection** — collection says where an asset belongs, object type says what it is. If absent: refuse acceptance; keep the asset uncatalogued or incomplete; issue a missing-field or blocked-work notice; optionally recommend a likely type; require explicit human or authorised-source confirmation before acceptance. |
| 4 | **Candidate validation** | A worker-nominated candidate is validated before human approval: **SUBMITTED → PENDING_REVIEW → VALIDATED → APPROVED → CURRENT**. A human-placed asset keeps the direct acceptance path when a real human explicitly places and accepts it; no redundant second approval. |
| 5 | **Library nominations** | Library **may not nominate candidates to itself.** Library may classify, validate, detect conflicts, detect expired, changed, missing or uncatalogued assets, issue conflict notices and blocked-work alerts, and recommend corrective action. A human, Intelligence, Publisher, or an authorised Dispatch workflow submits the resulting candidate. |
| 6 | **Approver identities** | Refused as approvers: **INTELLIGENCE, PUBLISHER, LIBRARY, JOE, DISPATCH, SYSTEM, AUTOMATION, COMI, EMAIL_HELPER.** If Mike approves through Joe, Mike Zachary is the approver; Joe may be recorded as the capture channel or evidence source, never as the approver. |
| 7 | **Plan v2** | Commit and push this document to the Library branch, recording the rulings, the schema and its verification, the Publisher `get_recipe` gap, the duplicate Dispatch JSON Library, the obsolete S1–S5 status, and the replacement and compatibility plan. |
| 8 | **Obsolete S1–S5** | The web-built S1–S5 implementation remains an **experimental historical record**, not accepted as Library v1 because it implements the superseded schema. Do not extend it with S6 or S7. Do not create real persistent Library data in it. Do not connect production Publisher, Intelligence, Joe, Dispatch, backup or `D:\Memory` use to it. |
| 9 | **Stop** | After committing and pushing, stop. Do not implement the corrected schema yet. Do not merge to main, modify `D:\Memory`, or disturb the Dispatch or Joe-Assistant working trees. |

### 0.1 What the rulings changed in the schema

The first draft (verification run 1, §7.1) was reviewed at **18 tables, 4 views, 31 triggers; 65
bad writes refused, 14 normal paths accepted.** Rulings 3–6 change the schema itself, so §2 now
carries them, and it was verified again (run 2, §7.2):

| Change | Ruling |
|---|---|
| Candidate statuses `SUBMITTED`, `PENDING_REVIEW`, `VALIDATED`, `APPROVED`, `REJECTED`, `DEFERRED`; a candidate enters as `SUBMITTED` | 4 |
| Version state `APPROVED_CURRENT` renamed `CURRENT` (COM "Approved Current"; the name the contract already uses) | 4 |
| Refused identities extended to nine, matched after normalising case, spaces and hyphens, so `Email Helper` and `email-helper` are refused as `EMAIL_HELPER` | 6 |
| `approval_record.capture_channel` and `capture_ref`: Joe recorded as the channel, never the approver | 6 |
| Candidate `recommended_object_type` (Library's recommendation) separate from `proposed_object_type` + `object_type_confirmed_by` (a human or the submitting source; never Library); validation requires the confirmation | 3, 5 |
| An approved candidate's object must carry the confirmed type and proposed collection | 3 |
| New `library_notice` table: missing-field, blocked-work, conflict, expired, changed, missing and uncatalogued notices with a recommended type and action; Library raises them and may not resolve them | 3, 5 |

---

## 1. Verified

The schema in §2 was executed on SQLite 3.50.4 (Python 3.14.5, Windows 11) by a script that reads
it **out of this document**, between the `BEGIN`/`END` markers, so what was tested is what is
written here. Results are in §7. No Library code was changed and no catalog file was created on
disk.

---

## 2. The corrected schema

Conventions:

- IDs are text with a readable prefix: `libobj_` (COM §3 immutable system ID), `libver_`, and
  plain ULID/UUID text elsewhere.
- Times are ISO-8601 UTC text, as the existing code writes them.
- **Refused identities** (ruling 6) are compared after
  `replace(replace(upper(trim(x)),' ','_'),'-','_')`, so spelling variants cannot slip through.
  SQLite has no shared constants, so the list appears in several `CHECK`s; a test must pin every
  copy to one Python constant, and the Python layer must normalise the same way (R22).
- The eighteen COM §4 object types likewise appear in four `CHECK`s and must be pinned together.
- `PRAGMA foreign_keys = ON` is per connection and is set again at every open (as
  `catalog/connection.py` already does). `journal_mode = WAL` is set at open, not here.

```sql
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
```

### 2.1 How a write looks

**A human places a document** (ruling 4 — direct acceptance, no second gate):

```
BEGIN IMMEDIATE
  INSERT library_object            -- first placement only; object_type given by the human
  INSERT approval_record           -- HUMAN_PLACED, APPROVED, approver = the human, version_id = new id
                                   -- capture_channel = 'JOE' if it arrived through Joe (ruling 6)
  INSERT library_version           -- CURRENT, approval_record_id = that record
COMMIT
```

**The object type is missing** (ruling 3):

```
-- no library_object, no version: acceptance refused
INSERT library_notice              -- MISSING_FIELD, missing_field = 'object_type',
                                   -- relative_path = the file, recommended_object_type = Library's guess
-- the file stays on the shelf; scans keep reporting it UNCATALOGUED
-- later, a human or authorised source confirms a type:
UPDATE library_notice SET status = 'RESOLVED', resolved_by = <human>, resolution = 'confirmed FORM_TEMPLATE'
-- then the placement above runs with that type
```

**Superseding** (the one transaction S3 requires):

```
BEGIN IMMEDIATE
  UPDATE library_version SET lifecycle_state = 'SUPERSEDED' WHERE version_id = <current>
  INSERT approval_record           -- for the new version
  INSERT library_version           -- later MAJOR.MINOR, supersedes_version_id = <current>
COMMIT
```

Out of order, the database refuses: inserting before the flip hits the one-current index and the
supersession trigger; an approval naming a version that never arrives fails its deferred foreign
key at `COMMIT`.

**A worker nominates** (rulings 3, 4, 5):

```
INSERT library_candidate           -- SUBMITTED, by Human / Intelligence / Publisher / Dispatch+Mission Record
UPDATE … status = 'PENDING_REVIEW'
UPDATE … recommended_object_type   -- Library classifies: a recommendation only
UPDATE … proposed_object_type, object_type_confirmed_by, object_type_confirmed_at
                                   -- the submitting source or a human confirms
UPDATE … status = 'VALIDATED', validation_result = 'PASSED'   -- Library validates

BEGIN IMMEDIATE                    -- the human decision, one transaction
  INSERT library_object            -- if new; object_type = the confirmed type
  INSERT approval_record           -- CANDIDATE_REVIEW, APPROVED, approver = the human, candidate_id
  INSERT library_version           -- CURRENT
  UPDATE library_candidate SET status = 'APPROVED', reviewed_by = <same human>
COMMIT
```

---

## 3. Field-by-field trace to the Core Object Model

**Status key:** **Stored** — a column of that name or its direct equivalent. **Table** — a row set.
**Derived** — computed by a view, deliberately not stored (reason given). **Choice** — the COM
names the field but not its values; the values chosen are listed for review.

### 3.1 COM §3 base schema

| COM group | COM field | Where in v2 | Status |
|---|---|---|---|
| Identity | `library_object_id` | `library_object.library_object_id`, `libobj_…`, immutable by trigger | Stored |
| | `object_code` | `library_object.object_code`, unique, immutable; stored **without** the `-v{MAJOR.MINOR}` suffix | Stored — **Choice**: see R10 |
| | `object_type` | `library_object.object_type`, the eighteen COM §4 types; required, never inferred (ruling 3) | Stored |
| | `collection` | `library_object.collection_id` → `library_collection` | Stored |
| | `title` | `library_object.title` (current display) and `library_version.title` (as approved) | Stored |
| | `slug` | `library_object.slug`, unique within collection | Stored |
| | `canonical_name` | `library_object.canonical_name` | Stored |
| Status / version | `status` | `library_version.lifecycle_state`; `library_candidate.status` before approval | Stored |
| | `version` | `library_version.version_major`, `version_minor` | Stored |
| | `is_current` | `library_version.is_current`, generated from `lifecycle_state` | Stored (generated) |
| | `effective_date` | `library_version.effective_date` | Stored |
| | `supersedes_id` | `library_version.supersedes_version_id` | Stored |
| | `superseded_by_id` | `library_version_lineage.superseded_by_version_id` | **Derived** — storing both directions creates two facts that can disagree |
| | `review_cycle` | `library_version.review_cycle` | Stored |
| | `review_due_date` | `library_version.review_due_date` | Stored |
| Authority | `owner_role` | `library_object.owner_role` (Manager refused) | Stored |
| | `approver` | `approval_record.approver` (nine identities refused, ruling 6) | Stored |
| | `approval_status` | `approval_record.approval_status`; `library_current.approval_status` | Stored |
| | `approval_record_id` | `library_version.approval_record_id` | Stored |
| | `approved_at` | `approval_record.approved_at` | Stored |
| | `authority_basis` | `approval_record.authority_basis` | Stored |
| Source / provenance | `source_refs[]` | `source_ref` rows | Table |
| | `created_from_workspace_id` | `library_version.created_from_workspace_id` | Stored |
| | `created_from_archive_id` | `library_version.created_from_archive_id` | Stored |
| | `source_confidence` | `library_version.source_confidence`, free text | Stored — values not set by the COM |
| | `no_fabrication_check` | `library_version.no_fabrication_check` `PASSED/FAILED/NOT_RUN` | Stored — **Choice** of values |
| Retrieval | `retrieval_tags[]` | `library_object_tag` | Table |
| | `consumer_roles[]` | `library_object_consumer` | Table |
| | `allowed_use` | `library_object.allowed_use` | Stored |
| | `access_level` | `library_object.access_level` | Stored |
| | `current_only_default=true` | `library_object.current_only_default` default 1 | Stored |
| Validation | `validation_gate` | `library_version.validation_gate` | Stored |
| | `validation_result` | `library_version.validation_result`; `library_candidate.validation_result` | Stored — **Choice** of values |
| | `drift_check_result` | `library_version.drift_check_result` (updatable by scans) | Stored |
| | `conflict_notice_id` | `library_version.conflict_notice_id` → `library_notice` | Stored |
| | `quality_check_result` | `library_version.quality_check_result` | Stored |
| Archive link | `archive_record_id` | `archive_link` type `ARCHIVE_RECORD` | Table |
| | `superseded_archive_id` | `archive_link` type `SUPERSEDED_VERSION` | Table |
| | `approval_archive_id` | `archive_link` type `APPROVAL_RECORD` | Table |
| | `retention_class` | `library_version.retention_class` | Stored |
| Relationships | `related_objects[]` `depends_on[]` `used_by[]` `replaces[]` `derived_from[]` | `object_relationship.relationship_type` `RELATED/DEPENDS_ON/USED_BY/REPLACES/DERIVED_FROM` | Table |

### 3.2 COM §3 rules

| COM rule | Where enforced |
|---|---|
| Immutable system ID | `library_object_identity_is_immutable`; no delete trigger |
| Code `LIB-{COLLECTION}-{TYPE}-{SHORTNAME}-v{MAJOR.MINOR}` | Stem stored; suffix refused in the stem; full code derived in `library_current.versioned_code`. Stem format is **not** enforced by the database (R10) |
| MAJOR / MINOR semantics | Ordering enforced (`library_version_moves_forward`); *which* part to bump is a human judgment the database cannot see |
| Current retrieval = `is_current` and `approved` | `library_current` view; `retrieval_event_current_only_returns_current` |
| Superseded versions route to Archive, retrievable only for audit | `library_version_archived_needs_archive_link`; `ARCHIVE_REFERENCE_ONLY` outcome |
| Lifecycle Draft → … → Retention Review | **Candidate** (ruling 4): COM "Draft / Candidate" = `SUBMITTED`; "Submitted for Review" = `PENDING_REVIEW`; "Validated" = `VALIDATED`; the human decision = `APPROVED` / `REJECTED` / `DEFERRED`. **Version**: "Approved Current" = `CURRENT`; "Active Use" = `ACTIVE_USE`; "Review Due" = `REVIEW_DUE`; `SUPERSEDED`; "Archived Version Record" = `ARCHIVED_VERSION_RECORD`; "Retention Review" = `RETENTION_REVIEW`. "Retained/exported/deleted by authority" = `archive_review_queue.disposition`. Transitions enforced by trigger in both tables |

### 3.3 COM §9 minimum entity structure

| COM §9 table | v2 | Notes |
|---|---|---|
| `library_collections(collection_id, name, purpose, owner_role, archive_policy, active)` | `library_collection` | All six columns. The closed fifteen by `CHECK`. `purpose`, `owner_role`, `archive_policy` seeded empty — no doctrine text invented |
| `library_objects(… current_version_id …)` | `library_object` | `current_version_id` **Derived** in `library_current`: SQLite cannot check a stored pointer at commit, so it could drift. `status`, `is_current` live on the version |
| `library_versions(version_id, library_object_id, version, content_uri, content_hash, effective_date, review_due_date, supersedes_version_id, approval_record_id, archive_record_id, created_at)` | `library_version` | `content_hash` → `content_sha256`; `archive_record_id` → `archive_link` |
| `library_metadata(metadata_id, library_object_id, key, value, value_type)` | `library_metadata` | Adds optional `version_id` for version-bound values |
| `approval_records(approval_record_id, object_id, version_id, approver, approval_status, approval_basis, approved_at, notes)` | `approval_record` | Adds `candidate_id`, `authority_basis`, `capture_channel`, `capture_ref` |
| `archive_links(archive_link_id, library_object_id, archive_record_id, relationship_type, description)` | `archive_link` | Adds `version_id`, `approval_record_id`, `created_at` |
| `library_candidates(candidate_id, proposed_object_type, proposed_collection, source_refs_json, submitted_by_role, status, validation_result)` | `library_candidate` | `source_refs_json` → `source_ref` rows. Adds recommended vs confirmed type (ruling 3) |
| `retrieval_events(retrieval_id, consumer_role, object_id, version_id, purpose, current_only, retrieved_at)` | `retrieval_event` | Adds `requested_object_code` and `outcome`, because a MISSING retrieval has no object id |
| `object_relationships(relationship_id, from_object_id, to_object_id, relationship_type, active)` | `object_relationship` | Adds `created_at` |

### 3.4 Beyond the COM, and why

| v2 element | Authority |
|---|---|
| `relative_path`, `content_sha256`, `size_bytes`, `observed_at` | Owner instruction D (shelf binding); v1 §2 shelf model |
| `library_notice` | v2 rulings 3 and 5; COM §8 outputs "Missing-item notice" and "Conflict Notice" |
| `capture_channel`, `capture_ref` | v2 ruling 6 |
| `recommended_object_type`, `object_type_confirmed_by/_at` | v2 rulings 3 and 5 |
| `publisher_recipe`, `recipe_requirement` | `DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md` §4.2; v1 ruling 6 |
| `catalog_scan`, `catalog_finding` incl. `UNMAPPED_FOLDER`, `PLACEMENT_CONFLICT` | Owner instruction D; v1 rulings 4 and 5 |
| `archive_review_queue` | `ARCHIVE_REVIEW_POLICY.md` §2–4 |
| `mission_record_id`, `workflow_event_id`, `HUMAN`/`DISPATCH` submitters | v1 ruling 3; v2 ruling 2 |
| Nine refused approver identities, normalised | v2 ruling 6 |
| Manager refused in `owner_role`, `consumer_role` | v1 ruling 3: no Manager component |
| `LIBRARY_INDEX_MANIFEST` allowed in **Index** | v1 ruling 2 overrides COM §4's Reference placement. The database does not pair object types with collections (R14) |

---

## 4. Compatibility trace

### 4.1 `taxonomy.py`

Unchanged. `library_collection`'s `CHECK` list and seed rows must equal `COLLECTIONS`; a test pins
the three against each other.

### 4.2 `models.py`

All changes are **additive** (ruling 2): new fields carry defaults, and no existing field is
renamed or removed.

| Field today | v2 | Effect |
|---|---|---|
| `LibraryObject.object_code` | `library_object.object_code` | Same meaning. Existing codes (`TPL-BROKER-CLOSEOUT`) are valid stems |
| `.collection` | `library_object.collection_id` | Same values |
| `.title` | `library_version.title`, mirrored to `library_object.title` | Same |
| `.version: int` | `version_major` + `version_minor` | **Additive**: `version_minor: int = 0`. Every existing caller reads `n` as `n.0` |
| `.status` `CURRENT` | `CURRENT`, `ACTIVE_USE`, `REVIEW_DUE` | Same name for the base state; reads back as `CURRENT` |
| `.status` `SUPERSEDED` | `SUPERSEDED`, `ARCHIVED_VERSION_RECORD`, `RETENTION_REVIEW` | Reads back as `SUPERSEDED`; finer state beside it |
| `.status` `DRAFT_CANDIDATE` | No version row; a draft is a `library_candidate` | **Breaking** for `add_version(status=DRAFT_CANDIDATE)` (R5) |
| `.source` `HUMAN_PLACED` / `APPROVED_CANDIDATE` | `approval_record.approval_basis` `HUMAN_PLACED` / `CANDIDATE_REVIEW` | Derived on read; enum unchanged |
| `.body_or_uri` | `content_uri`, plus `body` or `relative_path` | Same string kept in `content_uri` |
| `.accepted_by`, `.accepted_at` | `approval_record.approver`, `.approved_at` | Same |
| `.supersedes_version: int` | `supersedes_version_id` | Translated on write and read |
| `.tags` (per version) | `library_object_tag` (per object) | Per-version tag history not kept (R12) |
| — | `object_type`, `slug`, `canonical_name` | **Additive, required at acceptance.** Optional on the dataclass; the catalog refuses acceptance without `object_type` and raises a MISSING_FIELD notice (ruling 3) |
| `LibraryCandidate.submitted_by: SubmittedBy{INTELLIGENCE, PUBLISHER}` | `submitted_by_role` + `HUMAN`, `DISPATCH` | **Additive** enum members, mirrored in the Intelligence repo and `DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md` together |
| `.status` `PENDING_REVIEW` (default) | `SUBMITTED` on insert, then `PENDING_REVIEW` | `PENDING_REVIEW` keeps its name and meaning. `SUBMITTED` and `VALIDATED` are additive. The catalog writes both steps in one transaction for a caller that submits the old way |
| `.status` `APPROVED` / `REJECTED` | Same | Same |
| — | `recommended_object_type`, `proposed_object_type`, `object_type_confirmed_by/_at`, `submitted_by_name`, `mission_record_id`, `workflow_event_id`, `validation_result` | **Additive**, default `None` / `NOT_RUN` |
| `PublisherRecipe` + `RecipeSourceDetail` (S8) | `publisher_recipe` + `recipe_requirement` | Lossless |
| `RESERVED_SYSTEM_IDENTITIES` `{INTELLIGENCE, PUBLISHER, LIBRARY, SYSTEM, AUTOMATION}` | + `JOE`, `DISPATCH`, `COMI`, `EMAIL_HELPER`, normalised | **Additive** to the set; the comparison must normalise spaces and hyphens as the database does (R22) |

### 4.3 `registry.py` — the five-method surface

| Method | v2 behaviour |
|---|---|
| `add_version(obj)` | One `BEGIN IMMEDIATE` transaction: flip current → insert approval → insert version. Refuses `DRAFT_CANDIDATE` (R5) and a missing `object_type` (ruling 3) |
| `next_version(code) -> int` | Next **major**. Minor bumps through a new, additive method (R10) |
| `history(code)` | All versions, ordered by major, minor |
| `get_version(code, n)` | Returns `n.0` exactly (R10) |
| `all_object_codes()` | Unchanged |

`ObjectRegistry` (the dict) stays for tests. `tests/test_registry_contract.py` from S1–S5 is the
right harness to port: one suite against both registries. Its `DRAFT_CANDIDATE` case changes.

### 4.4 `resolver.py`

`current()` and `list_current(collection)` read `library_current`. Semantics the same. New:
`REVIEW_DUE` is current but blocked for external use, so Publisher must check `lifecycle_state`
(R11).

### 4.5 `ingestion.py`

| Function | v2 |
|---|---|
| `ingest_human_document(registry, code, collection, title, body_or_uri, accepted_by, tags)` | Direct acceptance kept, **no second gate** (ruling 4). Gains optional `object_type`, `slug`, `canonical_name`, `capture_channel`. Without `object_type` the catalog refuses and raises a MISSING_FIELD notice (ruling 3); the dict registry keeps working for tests |
| `submit_candidate` | Enters `SUBMITTED`, moves to `PENDING_REVIEW` |
| `review_candidate(…, approve, reviewed_by)` | Same human gate, same refusals, plus the four new identities. **New precondition**: `VALIDATED` with a confirmed type (ruling 4). New `classify_candidate()` (recommendation), `confirm_object_type()` (submitter or human), `validate_candidate()` (Library) |

### 4.6 `service.LibraryService`

Every existing method keeps its signature (ruling 2). Additions only: `classify_candidate`,
`confirm_object_type`, `validate_candidate`, `notices(status)`, `resolve_notice`, `get_recipe`.
`current()` and `list_current()` would record a `retrieval_event`, which turns a read into a write
(R19).

### 4.7 Publisher contract — `get_recipe` gap

`Publisher/src/dispatch_publisher/library_client.py`, read from GitHub on 2026-09-13, defines
`LibraryClient` as a Protocol of three methods:

| Protocol | `LibraryService` today | v2 |
|---|---|---|
| `current(object_code: str)` | Present | Unchanged |
| `resolve_packet(recipe_type: str)` | Takes `RecipeType`; a plain string works only because `RecipeType` is a `str` enum | Accept `str`; resolve against `recipe_requirement` kind `COMPANY_ITEM` |
| `get_recipe(recipe_type: str) -> dict` | **Absent.** The module states the signatures "mirror exactly"; they do not. A real `LibraryService` handed to Publisher fails on its first recipe lookup | Add it, returning a dict with the `required_library_object_codes` key `StubLibraryClient` reads, plus the S8 source fields |

This gap exists **today**, independent of v2.

### 4.8 Intelligence candidates

`LibraryCandidate` is field-locked to the Intelligence repo's dataclass. v2 adds fields with
defaults and enum members, and renames nothing, so a candidate built by today's Intelligence code
still crosses the boundary. What changes for Intelligence is behaviour after submission: its
candidate is not approvable until its object type is confirmed — by Intelligence itself as the
submitting source, or by a human — and Library has validated it. The Intelligence repo was **not
read** in this session; its dataclass must be compared field by field at the next review (§6.1).

### 4.9 Joe-Assistant — `Workers/worker_bus/host.py`

`LibraryWorker` calls only `service.current()` and `service.list_current(kind)`. Both keep their
signatures. When Mike approves through Joe, the approver is Mike Zachary and `capture_channel` is
`JOE` (ruling 6). `host.py` still builds `LibraryService()` in memory; pointing it at the catalog
is a Joe-Assistant change that needs its own authorisation.

### 4.10 Obsolete S1–S5 (`src/dispatch_library/catalog/`, schema version 1)

**Status (ruling 8): experimental historical record. Not accepted as Library v1. Not extended with
S6 or S7. No real persistent Library data in it. Not connected to production Publisher,
Intelligence, Joe, Dispatch, backup or `D:\Memory`.**

Commits `c767856`, `a3cceb8`, `5168a3f`, `aee174b`, pushed by another session on 2026-09-13
18:31–18:38 UTC. 169 tests. Verified 2026-09-13: no `catalog.db` exists anywhere on `D:`, and no
code in Joe-Assistant or Dispatch imports `dispatch_library.catalog`.

What its mechanism offers the replacement, as **patterns to copy, not code to extend**:

| File | What is worth carrying forward |
|---|---|
| `connection.py` | WAL outside the script with retry; per-connection foreign keys; busy timeout; refusal of a newer schema; one-transaction migration |
| `registry.py` | Flip + insert in one transaction over a shared connection |
| `queue.py` | Live handle + `flush()` inside the approval transaction |
| `shelf.py` | `walk_shelf`, `sha256_of`, ignore lists, dry-run-first, never-adopt |
| `service.py` | `review_candidate` as one transaction |
| `tests/test_registry_contract.py` | One suite against two registries |

**Replacement path — for decision at the next review (§6.1):**

| Option | What happens to `catalog/` | Trade-off |
|---|---|---|
| **A (recommended)** | Left in place, unchanged, as the historical record. A module banner and a guard that **refuses any on-disk path** (in-memory only) are added, so ruling 8's "no real persistent data" is enforced by code, not by memory. The corrected implementation is built in a new sibling package | Record intact and visibly fenced; two packages side by side until retirement |
| B | Rewritten in place; git history is the record | One package; the historical record exists only in history, and the rewrite is easy to mistake for an extension |
| C | Moved to an `experimental/` path | Clearly separated; moving it changes every import path its 169 tests use |

The new package name is for Mike to choose; a plain one such as `dispatch_library/persistence/`
fits ruling 7.

### 4.11 Dispatch's JSON Library — legacy projection inventory

**Status (ruling 1): legacy or temporary projection.** Not deleted, removed, migrated or replaced
in this mission. Read from git refs only; neither Dispatch working tree was touched.

**What it is.** `portal/models/library.py` — 243 lines on `sandbox/phase2-corrections`, 330 on
`joe/capture-to-card` (the branch checked out at `D:\Dispatch`, commit `411fb7a`, 2026-09-09, which
adds document upload). One JSON file, `get_memory_dir()/library.json`, plus on
`joe/capture-to-card` a `get_memory_dir()/LibraryDocuments/` folder. `get_memory_dir()` is
`DISPATCH_MEMORY_ROOT` if set, else the portal data directory. Six sections (`company`, `broker`,
`customer`, `location_intelligence`, `operations`, `intelligence`), not the fifteen collections.
Records are edited in place and deleted outright: no versions, no supersession.

**Public surface:** `get_all`, `get_section`, `add_record`, `add_document`¹, `document_path`¹,
`review_candidate`, `update_record`, `delete_record`, `get_available_company_assets`,
`get_missing_company_assets`; constants `SECTIONS`, `COMPANY_ASSETS`, `LOCATION_FIELDS`,
`RESERVED_SYSTEM_IDENTITIES`; `LibraryApprovalError`. ¹ `joe/capture-to-card` only.

**Production callers** (line numbers `sandbox/phase2-corrections` / `joe/capture-to-card`):

| Caller | Uses | Lines |
|---|---|---|
| `portal/routes/pages.py` — `GET /library` page | `get_all`, `get_missing_company_assets` | 791–794 / 787–790 |
| `portal/routes/api.py` — company asset status (two endpoints) | `get_available_company_assets`, `get_missing_company_assets` | 79–80, 130–131 / 102–103, 153–154 |
| `portal/routes/api.py` — `POST /library/add` | `add_record` | 253, 261 / 276, 284 |
| `portal/routes/api.py` — `POST /library/upload` | `add_document` | — / 296, 318 |
| `portal/routes/api.py` — `GET /library/document/<record_id>` | `document_path` | — / 330, 337 |
| `portal/routes/api.py` — `POST /library/review` | `review_candidate` | 273, 288 / 344, 359 |
| `portal/routes/api.py` — `POST /library/update` | `update_record` | 294, 301 / 365, 372 |
| `portal/routes/api.py` — `POST /library/delete` | `delete_record` | 312, 319 / 383, 390 |
| `portal/models/intelligence.py` | `add_record(submitted_by="machine")` | 171 / 169 |
| `portal/models/operations_feed.py` | `get_missing_company_assets` | 256 / 300 |
| `reconciliation/adapters/library_adapter.py` | Translates the `get_all()` dict into `LibraryObject`s (pure function over the dict) | 7, 70 |

**Coupled, not calling:** `portal/models/driver_pin_registry.py` (shares the `get_memory_dir()`
root); `portal/models/integrations_registry.py` (copies `update_record`'s convention).
**Tests that pin it:** `tests/test_portal.py`, `tests/test_operations_feed.py`,
`tests/test_backup_restore.py`, `tests/test_storage_routing.py`, and on `joe/capture-to-card`
`tests/test_library_documents.py`.

**On disk, 2026-09-13:** no `library.json` under `D:\Dispatch` or `D:\Dispatch Operations` (six
levels deep), and none, nor a `LibraryDocuments` folder, in `D:\Memory`.

**Conflicts with the authoritative Library** (none acted on):

1. With `DISPATCH_MEMORY_ROOT=D:\Memory` it writes `library.json` and `LibraryDocuments\` **into the
   shelf root** — a loose root file and a nineteenth, unmapped folder (R21).
2. `delete_record` deletes; `update_record` edits in place. The authoritative Library never does
   either.
3. Human-placed records are approved automatically (consistent with ruling 4), but machine
   records are approved by `review_candidate` with no validation step and no confirmed object type
   (rulings 3, 4).
4. Its `RESERVED_SYSTEM_IDENTITIES` lacks `JOE`, `DISPATCH`, `COMI`, `EMAIL_HELPER` and does not
   normalise (ruling 6).

**Compatibility plan** (proposal; each phase needs its own authorisation and is a Dispatch change):

| Phase | Change | Callers kept working by |
|---|---|---|
| P0 | This inventory | — |
| P1 | Library exposes a bounded read interface returning the shape `get_all()` / `get_section()` return today | Nothing in Dispatch changes |
| P2 | Portal reads (`/library` page, asset status, operations feed) switch to it behind a setting, with a parity test against the JSON | The JSON stays the default until parity passes |
| P3 | Writes route to the authoritative paths: `add_record`/`add_document` → placement (human) or candidate (machine); `review_candidate` → validation + approval. `update_record` and `delete_record` have no equivalent — versions and supersession replace them — and need design with Mike | Old routes keep their URLs and response shapes |
| P4 | `library.json` frozen as a read-only projection | Readers see the same data |
| P5 | Retirement, by Mike's decision | — |

### 4.12 S8 / S9 work (`recipes.py`, `shelf_mapping.py`)

Unchanged. `publisher_recipe` stores what `load_recipe_registry` already produces. The approved
mapping becomes a `LIBRARY_INDEX_MANIFEST` object in **Index**, and a scan records which mapping
version it applied (`catalog_scan.mapping_version_id`).

---

## 5. Migration and contract risks

### 5.1 Resolved by owner ruling

| # | Was | Resolution |
|---|---|---|
| R1 | Two Libraries | The Library repository is authoritative; Dispatch's JSON is a legacy projection, inventoried in §4.11 (ruling 1) |
| R2 | Shared-contract extensions | Approved as additive changes (ruling 2) |
| R3 | `object_type` required, no caller supplies it | Required; never inferred; refuse, keep uncatalogued, raise a notice, recommend, require confirmation (ruling 3) |
| R4 | Validation before candidate approval | Required for worker nominations; human placement keeps direct acceptance (ruling 4) |
| R16 | May Library nominate? | No. Library classifies, validates, detects, notifies and recommends (ruling 5) |
| R17 | Is Joe a refused approver? | Yes, with COMI and EMAIL_HELPER; Joe may be the capture channel (ruling 6) |

### 5.2 Open

| # | Risk | Why it matters | Proposed handling |
|---|---|---|---|
| R5 | `DRAFT_CANDIDATE` versions cease to exist | `test_registry_contract.py` line 101 adds one | Drafts become candidate rows; that test changes |
| R6 | **The database refuses system identities by name only.** It cannot prove that the string `Mike Zachary` was entered by Mike | The strongest true statement is "no system identity", not "a verified human". `capture_channel = JOE` records how an approval arrived; it is not proof of who gave it | Stated as a limit. Proof of the person belongs to Security (Matrix Phase 6, "Session Proof Chain") and is not claimed |
| R7 | An object row can exist briefly with no version (no deferred triggers in SQLite) | A crash between inserts could leave an orphan | One transaction; `library_object_without_version` reports any orphan |
| R8 | Generated columns and deferred foreign keys need SQLite ≥ 3.31 | Verified on 3.50.4 here; not on Mike's truck laptop | Check at I1; refuse to open below 3.31 |
| R9 | S1–S5 wrote schema version 1 | No data to migrate today | v2 is a fresh schema; a version-1 file is refused, not converted |
| R10 | Integer `version` in the contract vs COM `MAJOR.MINOR` | `get_version(code, 1)` is ambiguous once `1.1` exists | Stem stored, versioned code derived; `get_version(code, n)` means `n.0`; minor bumps by a new method |
| R11 | `REVIEW_DUE` is current but blocked for external use | A consumer reading `current()` alone could publish an expired credential | `current()` reports `lifecycle_state`; Publisher refuses `REVIEW_DUE` |
| R12 | Tags move from version to object | Per-version tag history lost | Accept; COM defines retrieval tags on the object |
| R13 | Publisher's `get_recipe` missing from `LibraryService` today | First recipe lookup fails | Add in I9 (§4.7) |
| R14 | Object types do not pair with collections; Security has no COM object type | A Security object can only be typed by approximation | Mike to name a Security object type, or accept that none is catalogued yet |
| R15 | `current_version_id`, `superseded_by_id` derived, not stored | COM lists them as fields | Available in views under those names |
| R18 | A `DELETE` disposition is recorded, never executed | Versions cannot be deleted by design | Carrying out a Delete decision is a separate act to design with Mike |
| R19 | Retrieval events make every `current()` a write | Contention with the Portal on one laptop | WAL + busy timeout; measure at I6 |
| R20 | Archive IDs are strings with no foreign key | The catalog cannot prove an Archive record exists | Accept; Archive is a separate store |
| R21 | **The Dispatch JSON projection writes into the shelf root** when `DISPATCH_MEMORY_ROOT=D:\Memory` | `library.json` and `LibraryDocuments\` would appear as a loose file and an unmapped folder in every scan, and a second Library would sit inside the first one's shelf | Report, do not fix here. At P1, point the projection's storage outside the shelf root or add both names to the scan's known-projection list — Mike to choose |
| R22 | **Normalisation must match in Python and SQL** | Today Python compares `upper().strip()`; the database also folds spaces and hyphens. `Email Helper` would pass Python and fail the database — a refusal surfacing as a database error rather than a clear message | One Python function mirroring the SQL expression, pinned by a test against the database |
| R23 | **S1–S5 is importable and can open a real file today** | Nothing stops `open_library("D:/…/catalog.db")` creating real persistent data in it, which ruling 8 forbids | Option A in §4.10: a guard refusing on-disk paths. Not added in this mission (ruling 9) |
| R24 | Intelligence's `LibraryCandidate` was not read | The additive claim in §4.8 rests on the Library-side copy of a field-locked mirror | Compare field by field at the next review |

---

## 6. Implementation sequence

Each step ends with its own proof, and none starts until the one before it has passed. **Nothing
here runs until Mike clears the review in §6.1.**

### 6.1 The next review must confirm (ruling 9)

1. Compatibility with `LibraryService` — §4.3–4.6.
2. Compatibility with Publisher `LibraryClient`, including `get_recipe` — §4.7.
3. Compatibility with Intelligence candidates — §4.8, R24.
4. The path for replacing the obsolete S1–S5 implementation — §4.10, options A–C.
5. The handling of the duplicate Dispatch JSON Library without breaking callers — §4.11, P0–P5, R21.

### 6.2 Sequence after that review

| # | Step | Replaces | Proof required to close |
|---|---|---|---|
| I1 | Schema v2 in the package chosen in §4.10; `SCHEMA_VERSION = 2`; version-1 files refused; SQLite ≥ 3.31 check; collections seeded | S1 | Every case of §7.2 as pytest; parity tests for collections, object types and refused identities; `sqlite3.sqlite_version` on Mike's laptop |
| I2 | Additive contract changes in `models.py`, with paired Intelligence and contracts-document changes; one normalisation function (R22) | — | All existing tests pass unchanged on the dict registry; extension documented in all three places |
| I3 | Registry v2: five-method surface; `BEGIN IMMEDIATE` supersession | S2, S3 | Contract suite green on both registries; crash-between-flip-and-insert leaves exactly one current |
| I4 | Candidate queue v2; classify, confirm type, validate, approve in one transaction | S5 | Every ruling-3/4/5/6 refusal as a test |
| I5 | Shelf binding and scan v2; `UNMAPPED_FOLDER`, `PLACEMENT_CONFLICT`; MISSING_FIELD notices | S4 | Dry run against the real `D:\Memory` with a before/after SHA-256 listing showing no change |
| I6 | Metadata, source refs, archive links, relationships, retrieval events, notices behind service methods | — | Current-only retrieval of a `REVIEW_DUE` version refused |
| I7 | Archive Review Queue: current + 3 | S6 | Fifth version queues the first; nothing deleted |
| I8 | `catalog.db` in `Dispatch/dispatch/backup.py` `_SOURCES` | S7 | **Dispatch change; separate authorisation.** Restore test |
| I9 | Recipes into `publisher_recipe`; `LibraryService.get_recipe` | S8 persistence | Publisher's `StubLibraryClient` tests run against the real service |
| I10 | The approved folder mapping catalogued as a `LIBRARY_INDEX_MANIFEST` in Index | S9 finish | **Accepted by Mike himself**, not written with his name |
| I11 | Intelligence route into the durable queue | S10 | End-to-end candidate from Intelligence to a human decision |
| I12 | Dispatch projection P1–P4 (§4.11) | — | **Dispatch change; separate authorisation per phase.** Parity tests; every existing route keeps its URL and shape |
| I13 | **Local proof** | — | A real load run on Mike's laptop through Library → Publisher. Nothing above is finished until this passes |

---

## 7. Verification record

Every refusal below was raised **by SQLite** — a `CHECK`, a foreign key, a unique index, or a
trigger — never by Python. The script extracts §2's SQL from this file and builds a fresh
in-memory database per case.

### 7.1 Run 1 — the draft Mike reviewed

SQLite 3.50.4, 2026-09-13. **18 tables, 4 views, 31 triggers.** **65 bad writes refused, 14 normal
paths accepted, 0 failures.** Seeded collections equal `taxonomy.COLLECTIONS`.

Refused: a sixteenth collection; an unknown collection; a versioned `object_code`; an unknown
object type; changing or deleting an object; a version with no approval or with another version's
approval; six system identities as approver; a later version while v1 was current; the same **with
the supersession trigger dropped** (the one-current index held alone); versions not later, falsely
superseding, or entering superseded; editing hash or title; deleting a version; superseded back to
current; archiving without a link; a second current claim on one file by letter case; bad, uppercase
or half SHA-256 binding; absolute, escaping and backslash paths; an approval whose version never
arrived (deferred FK at `COMMIT`); Dispatch candidates without a Mission Record; nameless or
system-named human candidates; Manager or Library as source; a candidate entering approved;
approval without validation; skipped transitions; validation without classification; decisions
with no record or a different reviewer; editing or deleting approvals; Manager as consumer or owner;
current-only retrieval of superseded or review-due versions; editing or deleting retrieval events;
queuing a current version; retention review without the queue; archive dispositions with no or a
system decider; placeholder recipes with requirements or source fields; a second current recipe;
findings on finished scans; editing finished scans; CHANGED with no version; self-relationships;
cross-object metadata; editing a version's source.

Accepted: human placement; supersession 1.0 → 1.1 → 2.0; crash rollback; Dispatch candidate to
approval; all four sources entering; deferral and resubmission; the full Archive path to KEEP;
lifecycle moves among current states; the real `publisher_recipes.json` stored losslessly with three
placeholders; a scan with every finding type; three retrieval outcomes; metadata, sources, tags,
consumers, relationships and drift update; an Index manifest; orphan reporting.

### 7.2 Run 2 — after the v2 owner rulings

SQLite 3.50.4, 2026-09-13, against §2 as it now stands. **19 tables, 4 views, 34 triggers.**
**99 bad writes refused, 22 normal paths accepted, 0 failures.** Seeded collections equal
`taxonomy.COLLECTIONS`; the nine-identity approver list appears in six `CHECK`s and the object-type
list in four, all four type lists identical (18 types).

Every run-1 case was carried forward, adjusted to the renamed states and the new candidate
progression. The count rises because the identity refusals now test spelling variants and because
rulings 3–6 added cases:

| Ruling | Refused in run 2 (new or extended) |
|---|---|
| 3 | An object with no `object_type` (NOT NULL); changing an object's type; validating with no confirmed type; validating with only Library's recommendation; a confirmation time with no confirmer; changing a confirmed type without reconfirming; approving into an object of a different type, or a different collection, than confirmed; a MISSING_FIELD notice naming no field; a notice about nothing; a notice recommending a type outside COM §4 |
| 4 | A candidate entering as PENDING_REVIEW or APPROVED instead of SUBMITTED; SUBMITTED → VALIDATED skipping PENDING_REVIEW (transition trigger alone); PENDING_REVIEW → APPROVED with no record; a version entering under the retired name `APPROVED_CURRENT` |
| 5 | Library nominating to itself; Library confirming an object type; Library, Joe, `automation` or `Email Helper` resolving a notice; a resolution with no text; editing a resolved notice; deleting a notice |
| 6 | Approver `" publisher "`, `Dispatch`, `LIBRARY`, `system`, `AUTOMATION`, `Intelligence`, `Joe`, `" JOE "`, `comi`, `COMI`, `Email Helper`, `email-helper`, `EMAIL_HELPER`; human candidates named `Joe` or `email helper`; Joe as candidate source; Joe confirming a type; a different system confirming another's candidate; `Human` as a confirmer; an archive disposition decided by `joe`; a capture reference with no capture channel |

| # | Accepted in run 2 |
|---|---|
| A01 | A human places a document directly — no second gate (ruling 4) |
| A02 | **Mike approves through Joe: approver Mike Zachary, capture channel JOE** (ruling 6) |
| A03 | A human named `Joe Smith` approves — normalisation does not over-match |
| A04–A05 | Supersession 1.0 → 1.1 → 2.0; crash between flip and insert rolls back to one current |
| A06 | Dispatch candidate with a Mission Record: SUBMITTED → PENDING_REVIEW → classified by Library → type confirmed by Dispatch → VALIDATED → APPROVED by Mike → version CURRENT |
| A07 | Intelligence candidate, type confirmed by Intelligence as the submitting source |
| A08 | Publisher candidate, type confirmed by Mike |
| A09 | Human candidate by Mike: type confirmed by Mike, validated |
| A10 | Dispatch candidate tied to a workflow event |
| A11 | A confirmed type changed with a fresh confirmation |
| A12 | Deferred by Mike, back to PENDING_REVIEW |
| A13 | **Object type missing** (ruling 3): no object row; the file stays UNCATALOGUED; a MISSING_FIELD notice recommends `ROLE_DOCTRINE`; Mike resolves it |
| A14 | BLOCKED_WORK and CONFLICT notices raised by Library; a conflict resolved by Publisher as an authorised source |
| A15 | Superseded → Archive link → archived record → queue → RETENTION_REVIEW → KEEP by Mike |
| A16 | CURRENT → ACTIVE_USE → REVIEW_DUE → ACTIVE_USE with an EXPIRED notice linked as `conflict_notice_id` |
| A17 | The real `publisher_recipes.json` stored losslessly; three placeholders carry nothing |
| A18 | A scan with UNMAPPED_FOLDER, PLACEMENT_CONFLICT, UNCATALOGUED and CHANGED findings; counts derived |
| A19 | Retrieval events RETURNED, MISSING, ARCHIVE_REFERENCE_ONLY |
| A20 | Metadata, source refs, tags, consumers, relationships, drift update |
| A21 | An Index manifest in the Index collection |
| A22 | An object with no version is reported |

### 7.3 Not verified

- Behaviour under concurrent writers (two connections, WAL).
- The SQLite version on Mike's truck laptop (R8).
- Any Python code against this schema. None has been written.
- The Intelligence repository's `LibraryCandidate` (R24).
