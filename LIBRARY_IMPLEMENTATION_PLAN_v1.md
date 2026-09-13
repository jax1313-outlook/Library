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

> **Update 2026-09-13, local session — this schema is superseded and must not be built.**
> The Library Department Core Object Model (`D:\Library`) was read. It specifies fields and
> tables this schema does not carry, so under this plan's own rule (§11) the Core Object Model
> wins and this section is wrong. The gap is not a few columns: it is an immutable object id,
> `MAJOR.MINOR` versions, a nine-state lifecycle, separate version, approval, archive-link,
> metadata, relationship and retrieval-event tables, and a collections table this section
> explicitly rejects. It also names 14 collections, not 15. Field-by-field in §15. The SQL is
> kept below as the record of what was proposed.

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

## 4. Mapping `D:\Memory` folders to Library collections — **MAPPED, approved by Mike Zachary 2026-09-13**

> **Update 2026-09-13, local session.** Written from the real listing of `D:\Memory`:
> eighteen top-level folders, seventeen of them empty. Only `Company Library` holds files —
> sixteen, in the root and in `Agent Worker Constitutions\`. The table lives in
> `src/dispatch_library/shelf_mapping.py` and is re-checked against the drive by
> `python -m dispatch_library.shelf_mapping D:\Memory`. Mike Zachary approved the two-tier model
> and every row below in the owner ruling of 2026-09-13 (§16, rulings 4 and 5).
>
> | `D:\Memory` folder | Collection | Basis |
> |---|---|---|
> | Company Library | Company | name |
> | Broker Library | Broker | name |
> | Customer Library | Customer | name |
> | Location Intelligence | Location_Intelligence | name |
> | Templates | Templates | name |
> | Compliance | Compliance | name |
> | Procedures | Process | COM §4 SOP / Workflow — approved |
> | Manuals | Training | COM §4 Training Asset / Manual — approved |
> | Forms | Templates | COM §4 Form / Template — approved |
> | Insurance | Company | COM §4 Company Credential — approved |
> | Equipment | Company | COM §2, §4 Capability Asset — approved |
> | Certifications | Compliance | COM §4 Compliance Asset — approved |
> | Operational Intelligence | — unmapped | pending ownership review |
> | Receipts | — unmapped | pending ownership review |
> | Fuel | — unmapped | pending ownership review |
> | Drivers | — unmapped | pending ownership review |
> | Evidence | — unmapped | pending ownership review; COM §1.1 gives evidence to Archive |
> | Documents | — unmapped | pending ownership review |
>
> **Collections with no folder:** Constitution, Operations, Reference, Route_Intelligence,
> Publisher_Parts, Security, Index.
>
> **Placement conflicts:** all sixteen files in `Company Library` — see §16.3. Recommendations
> only; nothing is moved.
>
> **Rule 5 is not done.** Cataloguing this table as an `Index` object needs the persistent
> catalog, which waits on review of the corrected schema (`LIBRARY_IMPLEMENTATION_PLAN_v2.md`).
> Index, not Reference, per ruling 2.
>
> The original text of this section follows unchanged.

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
| **S8** | Publisher: `resolve_packet` against real recipes. | S1, **`publisher_recipes.json`** | **Loaded 2026-09-13** — 2 of 5 recipe types; see §15.3 |
| **S9** | The `D:\Memory` → collection mapping table, ingested as an `Index` object accepted by Mike. | S4, **the folder listing** | **Mapped 2026-09-13** — ingestion awaits Mike; see §4 |

> **Update 2026-09-13:** S1–S7 are **on hold** until a schema is redrawn from the Core Object
> Model (§15). S8 and S9 were done without the schema: both are in-memory/lookup work that does
> not depend on S1 or S4 as built.
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

> **Update 2026-09-13, local session.** `D:\Library` and `D:\Memory` have now been inspected, and
> the comparison against the Core Object Model has been made (§15). It found §3 wrong. The
> migration is small today: sixteen files, all in one folder. Still not claimed: that any object
> has been catalogued, that anything persists, or that Mike has accepted any mapping row.

---

## 15. Core Object Model reconciliation — 2026-09-13, local session

Sources read on Mike's machine: `D:\Library\Library Department Core Object Model.docx` (COM),
`Publisher_Product_001_L1-COS_Constitution_Package_v1.0.docx`, `publisher notes.docx`,
`publisher_recipes.json`, and a recursive listing of `D:\Memory`.

**As written, nothing in this section was decided.** Mike Zachary ruled on every conflict below
on 2026-09-13; the rulings are recorded in §16 and the text here is left as the record of what
was found.

### 15.1 COM §3 base schema against the §3 SQL

| COM field group | COM fields | §3 schema |
|---|---|---|
| Identity | `library_object_id` (immutable, `libobj_{ULID}`) | **Missing.** Key is `(object_code, version)` |
| | `object_code` as `LIB-{COLLECTION}-{TYPE}-{SHORTNAME}-v{MAJOR.MINOR}` | Present; no format |
| | `object_type`, `slug`, `canonical_name` | **Missing** |
| | `collection`, `title` | Present |
| Status / version | `version` as `MAJOR.MINOR` with defined bump rules | **Integer** |
| | lifecycle: Draft/Candidate → Submitted → Validated → Approved Current → Active Use → Review Due → Superseded → Archived Version Record → Retention Review | **3 states** |
| | `is_current`, `effective_date`, `superseded_by_id`, `review_cycle`, `review_due_date` | **Missing** |
| | `supersedes_id` | Partial: `supersedes_version` |
| Authority | `approver`, `approved_at` | ≈ `accepted_by`, `accepted_at` |
| | `owner_role`, `approval_status`, `approval_record_id`, `authority_basis` | **Missing** |
| Source / provenance | `source_refs[]`, `created_from_workspace_id`, `created_from_archive_id`, `source_confidence`, `no_fabrication_check` | **Missing** (`source` is a different thing: how it arrived) |
| Retrieval | `retrieval_tags[]` | ≈ `library_object_tag` |
| | `consumer_roles[]`, `allowed_use`, `access_level`, `current_only_default` | **Missing** |
| Validation | `validation_gate`, `validation_result`, `drift_check_result`, `conflict_notice_id`, `quality_check_result` | **Missing** |
| Archive link | `archive_record_id`, `superseded_archive_id`, `approval_archive_id`, `retention_class` | **Missing** |
| Relationships | `related_objects[]`, `depends_on[]`, `used_by[]`, `replaces[]`, `derived_from[]` | **Missing** |

COM §9 tables against §3: `library_collections` (§3 rejects a collections table on purpose —
**direct conflict**); `library_objects` + `library_versions` split (§3: one table; the COM's
`content_uri` + `content_hash` cover §3's shelf binding); `library_metadata`, `approval_records`,
`archive_links`, `retrieval_events`, `object_relationships` (**missing**); `library_candidates`
(present, different fields — see 15.2). §3 carries things the COM does not: `catalog_scan`,
`catalog_finding`, `archive_review_queue`, and the recipe tables.

### 15.2 Conflicts beyond the schema, for Mike

1. **14 or 15 collections.** COM §5 lists fourteen with no `Security`. `taxonomy.py` and
   `04_DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md` §7 (line 615) list fifteen including `Security`.
   The closed set is not changed here.
2. **Where the Index lives.** COM §4 puts "Library Index / Manifest" in *Reference*; §4 rule 5
   of this plan puts the mapping table in *Index*. COM §5 also lists an `Index` folder.
3. **Who may submit a candidate.** COM §8 takes candidates from Intell, Manager, Publisher,
   Dispatch or Human. `models.SubmittedBy` allows only `INTELLIGENCE` and `PUBLISHER`, and the
   `LibraryCandidate` shape is field-locked to the Intelligence repo.
4. **Manager and legacy naming.** The COM is titled L2-COS and assigns Library duties to Manager.
   §12 of this plan and `CLAUDE.md` §5.6 say Dispatch has no Manager component and legacy names
   are not propagated. "The COM wins" on fields does not settle whether it wins on these.
5. **Human-placed assets and the validation gate.** §5 of this plan: a human-placed document is
   CURRENT with no second gate. COM §7–8 routes candidates "from … Human" through validation.
   These may be consistent (a human placement is not a candidate); it needs saying.
6. **Two copies of the COM** on the drive (§4 findings).

### 15.3 S8 — `publisher_recipes.json`

Loaded by `recipes.load_recipe_registry(path)`, per the choice Mike Zachary made in the local session on 2026-09-13 and confirmed in ruling 6, to keep
`PublisherRecipe` unchanged and drop no field:

- `required_company_items` → `required_library_object_codes`; `required_publisher_items` →
  `required_publisher_parts`; `required_human_items`, `required_outputs`,
  `human_review_required` → `RecipeSourceDetail`, held beside the recipe.
- The file defines **two** recipes, `broker_onboarding` and `government_proposal`.
  `VISIBILITY_STATUS_PACKET`, `POD_PACKAGE` and `REVIEW_PACKAGE` remain scaffold, and
  `RecipeRegistry.is_scaffold()` reports it.
- The company items are **item keys** (`w9`, `authority`), not COM object codes
  (`LIB-COMPANY-W9-…`). Against the empty Library every one resolves `MISSING`, which is correct.
  Making them resolve needs the object-code rules in 15.1 settled first.
- The file has no intelligence requirements; none were invented.
- **Not wired.** `LibraryService` already accepts a recipe registry, but
  `Joe-Assistant/Workers/worker_bus/host.py` still builds the scaffold default. Changing that is
  a Joe-Assistant change and was not made.
- `publisher notes.docx` is an FMCSA MCS-150 completion checklist, not recipe content. It was not
  loaded.

---

## 16. Owner ruling — Mike Zachary, 2026-09-13

Given by Mike Zachary in the local session, in his own words, after §15 was reported. Recorded
here as he stated it; nothing below extends his approval beyond what he stated.

**The Core Object Model governs the persistent Library catalog. §3 must not be built where it
conflicts with it.** The corrected schema is in `LIBRARY_IMPLEMENTATION_PLAN_v2.md`.

### 16.1 Rulings

| # | Subject | Ruling |
|---|---|---|
| 1 | Collections | Keep the fifteen-collection taxonomy, **including Security**. Its absence from the older COM does not authorise removing it from the taxonomy or the Matrix. |
| 2 | Index | Keep **Index** as its own collection. It holds catalog maps, manifests, shelf mappings and other Library control records — **not** Reference. |
| 3 | Candidate sources | Mike/Human; Intelligence; Publisher; Dispatch **only when tied to a real Mission Record or workflow event**. Library may classify and validate candidates but may not approve its own nominations. No Manager component is created or restored. No system identity may manufacture human approval. |
| 4 | `D:\Memory` mapping | Two-tier model approved, with the six name matches and six doctrine-supported rows of §4. Operational Intelligence, Receipts, Fuel, Drivers, Evidence and Documents stay **unmapped**, reported truthfully, pending ownership review. No folder is forced into a collection. |
| 5 | Existing files | Worker constitutions and research papers in Company Library are **placement conflicts**. Not moved, renamed, deleted, rewritten or recatalogued. Recommendations may be stated: current worker constitutions → Constitution; approved reference or research → Reference; historical or superseded → Archive referral. Mike decides any relocation separately. |
| 6 | Recipes | S8 accepted. Every source field preserved. The shared contract stays stable unless a documented compatibility extension is required. The three unsourced types stay clearly marked as placeholders. |
| 7 | Naming | Current Dispatch terminology in new work. No L1-COS, L2-COS or Manager-component terms propagated. Historical documents not rewritten. Short plain names, never shortened past clarity. |

### 16.2 Evidence recorded for S8 and S9

- **Tests.** 49 passed when S8 and S9 were first reported. After the rulings were applied —
  tier renamed `DOCTRINE_SUPPORTED`/`UNMAPPED`, the ruling's exact rows pinned, placement
  conflicts added — **52 passed**, 0 skipped, on Python 3.14.5 / pytest 9.1.1, Windows 11. The
  two tests that read the real drive and the one that reads the real
  `D:\Library\publisher_recipes.json` ran; none was skipped.
- **Scan.** `python -m dispatch_library.shelf_mapping D:\Memory`, read-only, 2026-09-13:
  18 top-level folders; 16 files, all under `Company Library`; 6 name matches, 6
  doctrine-supported, 6 unmapped; every folder on disk is in the table; every table row is on
  disk; no loose files at the root; collections with no folder: Constitution, Operations,
  Reference, Route_Intelligence, Publisher_Parts, Security, Index.
- **No shelf file was changed.** A SHA-256, size and modification-time listing of every entry
  under `D:\Memory` (19 directories, 16 files) was taken before the ruling work began and
  compared after it; the two listings are identical. No code in this change writes under the
  memory root.

### 16.3 Placement conflicts — recommendations only

All in `D:\Memory\Company Library`. Nothing was moved. Held in code as
`shelf_mapping.PLACEMENT_CONFLICTS`.

| File | Kind | Recommended |
|---|---|---|
| `Agent Worker Constitutions\00_DISPATCH_WORKER_CONSTITUTION_ARCHITECTURE.md` through `09_SUBCONTRACTOR_BUILD_RULES.md` (10 files) | worker constitution | Constitution if current; Archive referral if historical |
| `Agent Worker Constitutions\README.md` | worker constitution | Constitution if current |
| `Agent Worker Constitutions\DISPATCH_WORKER_CONSTITUTION_PACKAGE_v1.zip` | worker constitution | Constitution — **byte-identical copies** of the eleven files beside it (SHA-256 compared) |
| `Operational Memory Systems in Organizations 1.docx` | research paper | Reference; the ` 1` suffix suggests a copy |
| `Freight Visibility for Regional Carriers 2.docx` | research paper | Reference; the ` 2` suffix suggests a copy |
| `Freight System Design Package – Cargo Van + Trailer Operation.docx` | research / design paper | Reference |
| `Library Department Core Object Model 1.docx` | design authority | Reference — same text as the `D:\Library` copy; which copy is canonical is Mike's call |

### 16.4 Still unresolved

- The six unmapped folders — ownership review.
- Which Core Object Model copy is canonical.
- Whether each worker constitution is current (Constitution) or historical (Archive referral).
- Cataloguing the mapping as an `Index` object — waits on the persistent catalog.
- Wiring the loaded recipes into `Joe-Assistant/Workers/worker_bus/host.py` — a Joe-Assistant change, not made.

### 16.5 S1–S5 were built against the superseded schema — not accepted

Four commits reached this branch on 2026-09-13 between 18:31 and 18:38 UTC, from another session,
before the owner ruling reached it: `c767856` S1, `a3cceb8` S2+S3, `5168a3f` S5, `aee174b` S4.
They add `src/dispatch_library/catalog/` (schema, `SqliteObjectRegistry`, `SqliteCandidateQueue`,
shelf scan, `CatalogLibraryService`) and four test files, 169 tests.

`catalog/schema.sql` **is the §3 schema of this plan**, table for table — the one §3 and the
owner ruling say must not be built where it conflicts with the Core Object Model. It has no
immutable object id, integer versions, three lifecycle states, and no approval-record,
archive-link, metadata, relationship, retrieval-event or collections table.

Mike Zachary's instruction on 2026-09-13: push S8/S9 on top and flag S1–S5; do not revert. So:

- **S1–S5 stay on the branch and are not accepted.** Nothing uses them: no `catalog.db` exists on
  `D:`, and no code in Joe-Assistant or Dispatch imports `dispatch_library.catalog`.
- Much of the mechanism is reusable (single-transaction supersession, WAL/busy-timeout
  connection handling, version refusal, read-only shelf scan, shared-connection approval). The
  trace is in `LIBRARY_IMPLEMENTATION_PLAN_v2.md` §4.
- Reverting, keeping, or rebuilding them is Mike's decision at the v2 review.