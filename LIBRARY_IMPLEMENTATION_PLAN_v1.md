# LIBRARY_IMPLEMENTATION_PLAN_v1

**Program:** Dispatch
**Authority:** Mike Zachary — final authority
**Status:** Plan. Nothing in this document has been built.
**Date:** 2026-09-13

---

## 0. What this plan is, and the one thing it cannot contain

The instruction was: *do not design a new Library; implement the Library that
already exists.* That is the right instruction, and this repository already
holds more of that Library than a reader might expect. The taxonomy is not a
proposal — it is fifteen closed collections in `src/dispatch_library/taxonomy.py`,
sourced from `04_DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md` §7. The approval model
is not a proposal — it is enforced in `models.LibraryObject.__post_init__` and
`ingestion.review_candidate()`. Versioning and supersession are not proposals.
They work. What does not exist is **persistence**: every one of those objects
lives in a Python dictionary and is gone when the process exits.

So this plan proposes no taxonomy, no collections, and no storage hierarchy. It
proposes a catalog that remembers what is already on the shelf.

**One section could not be written: §4, the mapping of `D:\Memory` folders to
Library collections.** `D:\Library` and `D:\Memory` are on the Windows host.
This session runs in a Linux container that has no access to either, and the
documents were not attached to the message. That is stated in full in §11 along
with exactly what would unblock it. Guessing the folder names would be inventing
a taxonomy — the specific thing the instruction forbids three times — so the
section is left open rather than filled in.

Everything else below is grounded in files read in this container, cited by path.

---

## 1. Current state

### 1.1 What already exists, and works

| Capability | Where | State |
|---|---|---|
| **Fifteen-collection taxonomy** | `src/dispatch_library/taxonomy.py` | Closed set, matching Matrix §7 exactly. `require_valid_collection()` raises on a sixteenth. |
| **Versioning** | `registry.ObjectRegistry.next_version()`, `add_version()` | Monotonic per `object_code`. `supersedes_version` set by the ingestion helpers. |
| **Automatic supersession** | `registry.add_version()` | Adding a CURRENT version flips the previous CURRENT to SUPERSEDED in the same call. No code path leaves two CURRENT. |
| **Current resolution** | `resolver.current()`, `list_current()` | Returns only CURRENT. Correctness rests on the supersession invariant above. |
| **Two acceptance paths** | `ingestion.py` | Human placement is immediately CURRENT with no second gate (Forbidden Movement: "Human-Placed Library Asset → Artificial Validation Loop"). Candidates require an explicit human review. |
| **Approval model** | `models.RESERVED_SYSTEM_IDENTITIES`, `ingestion.review_candidate()` | `accepted_by`/`reviewed_by` may not be `INTELLIGENCE`, `PUBLISHER`, `LIBRARY`, `SYSTEM`, `AUTOMATION`; a candidate may not be approved by its own submitter. |
| **Service surface** | `service.LibraryService` | `current`, `list_current`, `resolve_packet`, `submit_candidate`, `review_candidate`, `ingest_human_document`, `register_recipe`, `pending_candidates`. Matches Matrix §8. |
| **Publisher boundary** | `Publisher/src/dispatch_publisher/library_client.py` | A `LibraryClient` Protocol whose signatures mirror `LibraryService` exactly. No shared package dependency between the repos. |
| **Live Publisher wiring** | `Joe-Assistant/Workers/worker_bus/host.py` | `build_bus()` hands `LibraryWorker` a real `LibraryService`; LIBRARY reports `LIVE`. Proven end to end 2026-09-13 (`Joe-Assistant/TEST_EVIDENCE.md` §8). |
| **Backup of the shelf** | `Dispatch/dispatch/backup.py` `_SOURCES` | `DISPATCH_MEMORY_ROOT` is already a first-class backup source: role `memory`, label `Memory`, recursive. |
| **Archive retention policy** | `ARCHIVE_REVIEW_POLICY.md` §2–4 | Current + three previous retained; older enters an Archive Review Queue for Mike's Keep/Delete decision. Policy written, never implemented. |

### 1.2 What is missing

| Gap | Evidence |
|---|---|
| **No persistence.** `ObjectRegistry`, `CandidateQueue`, `RecipeRegistry` are dicts. | `KNOWN_GAPS.md` "Architectural gaps carried forward"; confirmed by reading `registry.py`. Phase A had to run as one process for this reason (`Joe-Assistant/KNOWN_LIMITATIONS.md` §14). |
| **No shelf binding.** `body_or_uri` is a string. Nothing connects an object to a file under `D:\Memory`. | `models.LibraryObject` has no path, hash, or size field. |
| **Recipe content is scaffold.** Five doctrine-named types, all with empty requirement lists. | `recipes.py` module docstring: "SCAFFOLD — PENDING REAL SOURCE: `publisher_recipes.json` was not found in any repo in scope." |
| **No Archive Review Queue.** SUPERSEDED is marked; nothing queues, reports, or acts on the current+3 rule. | `KNOWN_GAPS.md`; no queue in the source tree. |
| **No Intelligence route.** `LibraryCandidate` is field-identical to the Intelligence repo's, but nothing calls `submit_candidate` from Intelligence. | `docs/OBJECT_MODEL.md`; no caller in either repo. |
| **No drift detection.** A human editing a file on the shelf is invisible to the Library. | Follows from the absence of shelf binding. |

### 1.3 Reusable unchanged

`taxonomy.py`, `models.py`, `resolver.py`, `ingestion.py` and the `LibraryService`
facade need **no changes**. Persistence goes in behind them. That is the whole
point of the plan's shape: `ObjectRegistry` already has a narrow, five-method
surface (`add_version`, `next_version`, `history`, `get_version`,
`all_object_codes`), and `docs/OBJECT_MODEL.md` already anticipates this —
"a Spine-backed persistence layer would implement the same surface."

**The approval model must not be touched.** It is the strongest thing in this
repository and it fired correctly four times unprompted during Phase A.

---

## 2. Architecture

```
  D:\Memory                      the shelf — the physical assets, unchanged
        │                        Dispatch already knows it as DISPATCH_MEMORY_ROOT
        │                        (portal.models.get_memory_dir)
        │
        │   catalogued by relative path + SHA-256, never moved, never renamed
        ▼
  catalog.db  (SQLite)           the catalog — what exists, which version is
        │                        current, who accepted it, what superseded it
        ▼
  ObjectRegistry surface         unchanged five-method contract
        ▼
  LibraryService                 unchanged service surface (Matrix §8)
        ▼
  Publisher · Intelligence · Joe
```

**The database is the catalog. `D:\Memory` is the shelf.** The catalog never
becomes a second copy of a document: for a shelf-backed object, `body_or_uri`
holds the relative path and the bytes stay where Mike put them. Library manages
existing assets rather than replacing them.

Two consequences worth stating plainly:

- **A file on the shelf that the catalog has never seen is not a Library object.**
  It is an uncatalogued file, and the scan reports it as such. It is not
  silently adopted, because adoption is an acceptance and acceptance needs a
  human name on it.
- **A catalog row whose file has vanished is a defect, not a deletion.** It is
  reported. The Library does not quietly forget an object because a file moved.

---

## 3. Recommended SQLite schema

Verified on SQLite 3.45.1 before being written here: the script below executes
as given (10 tables), and eight refusals were exercised directly against it —
a second CURRENT version of one `object_code`; two objects claiming one shelf
file; a system identity as `accepted_by`; a pending candidate carrying a
reviewer; an approved candidate carrying none; a submitter approving its own
candidate; a system identity as `reviewed_by`; and an archive disposition with
no name on it. Each was refused by the database. A real human approval and a
pending queue entry were accepted.

This verifies that the schema does what it says. It does **not** verify the
schema against the Library Department Core Object Model — see §14.

```sql
PRAGMA foreign_keys = ON;
-- journal_mode = WAL is set out of band at open time. It does not honour
-- busy_timeout, which is why it is not in this script.

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

    -- the shelf. NULL for an object whose body is inline rather than a file.
    relative_path      TEXT,      -- under DISPATCH_MEMORY_ROOT, POSIX separators
    content_sha256     TEXT,
    size_bytes         INTEGER,
    observed_at        TEXT,      -- when the catalog last verified the file

    PRIMARY KEY (object_code, version),
    CHECK (version > 0),
    CHECK (accepted_by <> ''),
    -- The Hard Rule, in the database rather than only in Python. A future
    -- caller that bypasses the dataclass still cannot write a system identity
    -- into an approval field.
    CHECK (upper(trim(accepted_by)) NOT IN
           ('INTELLIGENCE','PUBLISHER','LIBRARY','SYSTEM','AUTOMATION'))
);

-- The resolver's correctness condition, enforced by the database. Today it is
-- guaranteed by one careful function; after this it is guaranteed by SQLite.
CREATE UNIQUE INDEX library_object_one_current
    ON library_object (object_code) WHERE status = 'CURRENT';

-- One current object per shelf file. Two objects claiming the same document is
-- a cataloguing error, and it is better refused at write time than discovered
-- by a Publisher packet that resolves twice.
CREATE UNIQUE INDEX library_object_path
    ON library_object (relative_path)
    WHERE relative_path IS NOT NULL AND status = 'CURRENT';

CREATE INDEX library_object_shelf ON library_object (collection, status);

CREATE TABLE library_object_tag (
    object_code TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    tag         TEXT    NOT NULL,
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

    -- A reviewed candidate has a reviewer; a pending one does not. Keeps an
    -- approval from existing without a name attached to it.
    CHECK ((status = 'PENDING_REVIEW' AND reviewed_by IS NULL)
        OR (status <> 'PENDING_REVIEW' AND reviewed_by IS NOT NULL)),
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

-- ARCHIVE_REVIEW_POLICY.md §2-4: current + three previous are retained
-- automatically; older versions queue for Mike's Keep/Delete decision. Nothing
-- is ever deleted by this table -- it prepares a decision, it does not make one.
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
    CHECK ((disposition = 'PENDING' AND decided_by IS NULL)
        OR (disposition <> 'PENDING' AND decided_by IS NOT NULL))
);

-- Every scan of the shelf, so drift is a record rather than a console message.
CREATE TABLE catalog_scan (
    scan_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT    NOT NULL,
    finished_at TEXT,
    memory_root TEXT    NOT NULL,
    files_seen  INTEGER NOT NULL DEFAULT 0,
    catalogued  INTEGER NOT NULL DEFAULT 0,
    uncatalogued INTEGER NOT NULL DEFAULT 0,
    changed     INTEGER NOT NULL DEFAULT 0,   -- hash differs from the catalog
    missing     INTEGER NOT NULL DEFAULT 0    -- catalogued, file not on the shelf
);

CREATE TABLE catalog_finding (
    scan_id       INTEGER NOT NULL REFERENCES catalog_scan (scan_id) ON DELETE CASCADE,
    relative_path TEXT    NOT NULL,
    finding       TEXT    NOT NULL CHECK (finding IN ('UNCATALOGUED','CHANGED','MISSING')),
    detail        TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (scan_id, relative_path, finding)
);

CREATE TABLE schema_version (version INTEGER NOT NULL);
```

**Note on `collection`.** It is deliberately *not* a foreign key to a
`collection` table. The fifteen collections are a closed set in doctrine, and
`taxonomy.require_valid_collection()` already enforces it at the only place
objects are constructed. A collections table would be a second place to add a
sixteenth collection, which is the opposite of what a closed set means.

---

## 4. Mapping `D:\Memory` folders to Library collections — **OPEN**

**This section cannot be written from this container.** See §11.

What can be said now:

- The **target** side of the mapping is fixed and needs no decision: the fifteen
  collections in `taxonomy.py`.
- The **source** side is `D:\Memory`, whose actual folder structure has not been
  observed here.
- Three facts about `D:\Memory` *are* established from code in hand:
  - `Dispatch/dispatch/backup.py` treats it as a recursive backup source under
    `DISPATCH_MEMORY_ROOT`.
  - `Dispatch/bootstrap_d_drive.py:182` places uploaded evidence at
    `D:\Memory\Evidence`.
  - `Dispatch/dispatch_launcher/settings.py:133` describes it as "Where
    evidence, receipts and the library live."

So `D:\Memory` holds at least evidence, receipts, and the library, and evidence
already has its own subtree. That is not enough to write a mapping table, and a
mapping table written from three inferences would be the invented taxonomy the
instruction forbids.

**The mapping rules that will apply, once the listing is in hand:**

1. Every folder maps to exactly one of the fifteen collections, or to none.
2. A folder that maps to none is reported as **uncatalogued**, not forced into
   `Reference` to make the table look complete. An honest gap is worth more than
   a full table.
3. No folder is renamed, moved, or merged. The mapping is a lookup, not a
   migration of the shelf.
4. `Evidence` is expected to map to **no** collection: evidence belongs to
   Dispatch loads and to Archive, not to Library truth. This will be confirmed
   against the listing rather than assumed.
5. The mapping table itself becomes a catalogued Library object in the `Index`
   collection, accepted by Mike — so the mapping is versioned by the same
   machinery as everything else it governs.

---

## 5. Approval model — preserved exactly

No change is proposed. Restating it so that the persistence work cannot quietly
erode it:

| Path | Gate |
|---|---|
| Human places a document | `accepted_by` is the approval. **No second gate** — an artificial validation loop over a human-placed asset is a Forbidden Movement. The object is CURRENT immediately. |
| Intelligence or Publisher nominates | `PENDING_REVIEW` until `review_candidate(approve=True, reviewed_by=<human>)`. |
| Any approval field | May not be `INTELLIGENCE`, `PUBLISHER`, `LIBRARY`, `SYSTEM`, `AUTOMATION`. |
| Candidate self-approval | `reviewed_by` may not equal the submitter's own identity. |

The schema in §3 adds these as `CHECK` constraints so that they hold against a
caller that bypasses the dataclass — defence in depth, not a new rule. Phase A
confirmed all four fire unprompted (`Joe-Assistant/TEST_EVIDENCE.md` §8).

---

## 6. Versioning, current/superseded, and the Archive relationship

**Versioning.** Unchanged: `next_version()` is `max(version) + 1` per
`object_code`, and `supersedes_version` is set by the ingestion helpers. In the
catalog this becomes a query rather than a dictionary scan; the semantics do not
move.

**Current/superseded.** Unchanged, and now enforced twice: once by
`add_version()` flipping the previous CURRENT in the same transaction, and once
by the partial unique index. The registry write becomes a single transaction —
today the flip and the append are two statements over a dict, and a persistent
store makes the window between them real.

**Archive relationship.** `ARCHIVE_REVIEW_POLICY.md` is written and unimplemented.
This plan implements exactly what it says and nothing beyond:

- Current + three previous are retained automatically.
- Version `current − 4` and older enters `archive_review_queue` with
  `disposition = 'PENDING'`.
- **Nothing is deleted automatically.** The queue prepares a Keep/Delete decision
  for Mike's monthly report. `decided_by` is required for any non-pending
  disposition, so a disposition cannot exist without a name on it.
- A `DELETE` disposition removes the *catalog row*. Whether the file leaves the
  shelf is a separate, explicit act — the Library does not delete Mike's files
  as a side effect of a catalog decision.

---

## 7. Publisher integration

The boundary already exists and is correct: `LibraryClient` is a Protocol in the
Publisher repo mirroring `LibraryService`'s signatures, with no shared package
dependency (`07_DISPATCH_REPO_PLACEMENT_PLAN.md`). Persistence changes nothing
about that shape — a catalog-backed `LibraryService` satisfies the same Protocol.

Two things do change:

1. **`resolve_packet` becomes useful.** Today it returns `{}` for every recipe
   because `required_library_object_codes` is empty scaffolding. With real
   recipes loaded from `publisher_recipes.json`, it resolves each required code
   to a CURRENT object or to `MISSING` — and `MISSING` is what
   `create_missing_notice()` in `Publisher/src/dispatch_publisher/service.py`
   already exists to turn into a notice.
2. **Templates survive a restart.** Phase A proved the live path works
   (`PUBLISHER check_readiness` → `LIVE`, "Ready to assemble") but had to run as
   a single process. With the catalog, `python -m worker_bus ask PUBLISHER
   check_readiness ...` works as a separate command, which is how it will
   actually be used.

`publisher_recipes.json` is required for (1) and is not in this container. Until
it arrives, `recipes.py` stays scaffold and says so — it already does.

---

## 8. Intelligence integration

`LibraryCandidate` is field-identical to the Intelligence repo's dataclass of the
same name, deliberately, so a candidate crosses the repo boundary without
translation (`docs/OBJECT_MODEL.md`). What is missing is the call, not the shape.

With the catalog, the queue becomes durable, which is what makes the route worth
building: an Intelligence finding routed to Library survives until a human gets
to it, instead of until the process exits. `pending_candidates()` becomes the
query behind a review surface.

**Not in scope here:** the Portal review card. The System Relationship Matrix
assigns card creation to Manager/Portal, not Library — and Dispatch doctrine
(`CLAUDE.md` §5.6) has no Manager component. Library exposes
`pending_candidates()`; whatever renders it is a separate decision.

---

## 9. Migration requirements

The migration is a **catalog build**, not a data move. Nothing on `D:\Memory` is
moved, renamed, reorganised, or rewritten.

| Requirement | Detail |
|---|---|
| **Read-only against the shelf** | The first scan opens files to hash them and writes nothing to `D:\Memory`. D9: retrieval is not modification. |
| **Idempotent** | Re-running the scan over an unchanged shelf produces no catalog change and a scan record showing zero findings. |
| **No silent adoption** | A file that maps to a collection is *reported* as catalogable. It becomes a Library object only through `ingest_human_document` with a human's name — because that is what acceptance means. |
| **Object codes** | Derived from the mapping rules in §4, not invented per file. Blocked with §4. |
| **Dry run first** | The scan must be runnable in report-only mode and produce the full finding list before anything is written. |
| **Reversible** | The catalog is a single SQLite file. Deleting it and rescanning loses no asset, because the assets were never in it. |
| **Existing in-memory objects** | None to migrate. Nothing has ever persisted. |
| **Backup** | `catalog.db` must be added to `Dispatch/dispatch/backup.py` `_SOURCES`; `D:\Memory` is already covered. |

---

## 10. Implementation sequence

Ordered so that each step is provable on its own, and so the two blocked steps
sit late rather than in the middle.

| # | Step | Depends on | Blocked? |
|---|---|---|---|
| **S1** | Schema + migration runner + `schema_version`. Tests for both `CHECK` refusals and both uniqueness refusals. | — | No |
| **S2** | `SqliteObjectRegistry` implementing the existing five-method surface. `LibraryService` takes it by injection; the in-memory registry stays for tests. No change to `taxonomy`, `models`, `resolver`, `ingestion`. | S1 | No |
| **S3** | Make supersession one transaction. Test: a crash between the flip and the append leaves exactly one CURRENT. | S2 | No |
| **S4** | Shelf binding — `relative_path`, `content_sha256`, `size_bytes`; the scan; `catalog_scan` / `catalog_finding`; drift detection for a file edited in Explorer. | S2 | No |
| **S5** | Candidate queue to SQLite. Durable `pending_candidates()`. | S1 | No |
| **S6** | Archive Review Queue — current+3, PENDING dispositions, the monthly report's data. Nothing auto-deletes. | S2 | No |
| **S7** | Register `catalog.db` in `Dispatch/dispatch/backup.py` `_SOURCES`; restore-path test. | S1 | No |
| **S8** | Publisher: `resolve_packet` against real recipes. | S1, **`publisher_recipes.json`** | **Yes** |
| **S9** | The `D:\Memory` → collection mapping table, ingested as an `Index` object accepted by Mike. | S4, **the folder listing** | **Yes** |
| **S10** | Intelligence route: `route_to_library()` → durable candidate queue. | S5 | No |

S1–S7 and S10 are eight of ten steps and none of them are blocked. **The
persistence work can start now** and does not wait on `D:\Library`.

---

## 11. What is blocked, and what would unblock it

`D:\Library` and `D:\Memory` are on the Windows host. This session runs in a
Linux container. Neither is reachable, and the documents were not attached to
the message.

Searched, and not found anywhere in this container:

- `publisher_recipes.json`
- `technical_narrative_template.md`
- `past_performance_template.md`
- `quality_control_statement.md`
- `submission_email_template.md`
- any "Library Department Core Object Model" document
- any "Publisher Constitution Package"
- any `Memory` directory or mounted `D:` volume

This is not a new discovery. `KNOWN_GAPS.md` in this repository already records
that "Library Department Core Object Model" and `publisher_recipes.json` were
*not found in any repo in scope*, and `recipes.py` carries a `SCAFFOLD — PENDING
REAL SOURCE` banner naming the same file. The Library has been waiting for
precisely these documents. They now exist — on the other side of a boundary this
session cannot cross.

**What would unblock §4 and S9** (smallest useful thing first):

```
dir /s /b D:\Memory > memory_tree.txt
```

A recursive folder listing is enough to write the mapping table. File contents
are not needed for it.

**What would unblock S8:** `publisher_recipes.json` itself.

**What would let the plan be checked against its stated authority:** the "Library
Department Core Object Model" and the Publisher Constitution Package. §3 is
derived from the dataclasses in `models.py`, which are field-locked to
`DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md` §3.5 and §4 — a good anchor, but not the
Core Object Model itself. **If the Core Object Model specifies fields this schema
does not carry, the Core Object Model wins and §3 is wrong.**

---

## 12. Legacy terminology

Checked. No implementation file in this repository contains `L1-COS`, `L2-COS`,
Manager-as-component terminology, or legacy platform branding. The occurrences in
the wider repository set are in historical governance documents that explicitly
mark the terms as legacy — for example `DISPATCH_CONTEXT_MASTER_v2.md`: "L2-COS
is legacy terminology and should not be used as the current program name except
when quoting older source files."

`MANAGER.md` exists in this repository as a doctrine document. Dispatch doctrine
(`CLAUDE.md` §5.6) has no Manager component, and no code here references one.
Nothing in this plan introduces one; §8 routes around it deliberately.

Naming in this plan uses current Dispatch terminology throughout. Per §7 of
doctrine on not editing old decisions to hide history, no historical document is
rewritten — legacy names are left where they are, and not propagated forward.

---

## 13. The ten targets

| Target | Today | After |
|---|---|---|
| 1. Persistent | **No** — dicts | S1–S2 |
| 2. Versioned | **Yes** | preserved, DB-enforced |
| 3. Current-aware | **Yes** | preserved, DB-enforced |
| 4. Archive-aware | Partial — SUPERSEDED marked, nothing queues | S6 |
| 5. Approval-aware | **Yes, strongly** | preserved + `CHECK` constraints |
| 6. Publisher-consumable | **Yes** — proven live in Phase A | S8 makes recipes real |
| 7. Intelligence-consumable | Partial — shape matches, no route | S10 |
| 8. Backupable | **Yes** for the shelf | S7 adds the catalog |
| 9. Human-inspectable | **Yes** — files in folders | S4 adds drift detection |
| 10. Provider-neutral | **Yes** — SQLite + filesystem, no cloud dependency anywhere | unchanged |

Five of ten already hold. Three of the remaining five are unblocked today.

---

## 14. What this plan does not claim

- **Nothing here has been built.** This is a plan.
- **`D:\Library` and `D:\Memory` have not been inspected.** Required analysis
  steps 1 and 2 were not performed, and step 3 — comparing the actual structure
  against the Library Department Core Object Model — was not performed, because
  neither input is reachable from this container.
- **The schema is verified to execute, not verified against the Core Object
  Model.** It was run on SQLite 3.45.1 and its constraints were exercised. It is
  derived from `models.py`, not from the authoritative specification.
- **No estimate of the migration's size is given**, because that depends on the
  folder listing.
