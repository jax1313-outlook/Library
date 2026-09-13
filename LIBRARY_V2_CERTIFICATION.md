# LIBRARY_V2_CERTIFICATION

**Program:** Dispatch · **Authority:** Mike Zachary — final authority
**Mission:** OWNER AUTHORIZATION: BUILD LIBRARY V2 (Mike Zachary, 2026-09-13), on
`LIBRARY_IMPLEMENTATION_PLAN_v2.md` at `9747b74`.
**Machine:** the operator's Windows 11 Pro laptop · Python 3.14.5 · SQLite 3.50.4
**Date:** 2026-09-13

This records what was built, what was run on this machine, what it proved, what went wrong, and
what is still Mike's to do. Anything not listed as run here was not run.

---

## 1. The answer

**Yes.** The Library now remembers, in one SQLite catalog, and Publisher and Intelligence use that
memory across real process restarts. The Portal's JSON Library is contained behind compatibility
handling and cannot become a second authority: in catalog mode it reads and writes only through the
Library, and if the Library cannot be imported it refuses instead of falling back.

Two limits on that answer are real and stated in §8: the Dispatch branch the laptop actually runs
(`joe/capture-to-card`) does not yet carry the containment, and the operator's environment does not
yet name the catalog. Both need Mike.

---

## 2. Commits and branches

| Repository | Branch | Commits (this mission) |
|---|---|---|
| Library | `claude/dispatch-top-improvements-rwf14h` | `fefb647` catalog v2 · `6452f3b` renewal and retrieval roles · this record |
| Dispatch | `sandbox/phase2-corrections` | `9669364` JSON Library contained; catalog in backup |
| Joe-Assistant | `claude/dispatch-top-improvements-rwf14h` | `cc03244` persistent Library in the bus; Phase A across processes |
| Intelligence (`L2-intelligence-agent.`) | — | read only, no change needed |
| Publisher | — | read only, no change needed |

Nothing merged to main. `D:\Dispatch` (on `joe/capture-to-card`) and `D:\Joe Assistant` (on `main`)
were not checked out, edited or committed: Dispatch and Joe-Assistant work was done in git worktrees
in the session scratchpad, beyond the depth `dispatch_launcher/copies.py` searches, so no second
Dispatch copy was created where the launcher would find it.

The S1-S5 commits (`c767856`, `a3cceb8`, `5168a3f`, `aee174b`) remain in history; their code was
replaced in place by v2 and a schema-version-1 file is refused.

---

## 3. What was built

### Library (`src/dispatch_library/`)

| File | What |
|---|---|
| `catalog/schema.sql` | Plan v2 §2 verbatim; a test fails if it and the plan disagree |
| `catalog/connection.py` | SQLite ≥ 3.31 required; WAL; per-connection foreign keys; busy timeout; `CatalogBusyError`; v1, newer and foreign files refused |
| `catalog/store.py` | Every write in `BEGIN IMMEDIATE`: placement and supersession, retention queue, object-type refusal with notice, candidates, validation, decisions, notices, lifecycle and renewal, metadata, sources, Archive links, relationships, retrieval events, recipes, read-only shelf scan |
| `catalog/service.py` | `CatalogLibraryService` — every `LibraryService` signature kept; `get_recipe`, `availability`, `current_for_external_use`, candidate and notice operations; `open_library`, `open_configured_library` |
| `catalog/registry.py`, `catalog/queue.py` | The five-method registry and the candidate queue over v2 |
| `catalog/intake.py` | `DurableCandidateSink`: Intelligence's `route_to_library(..., store=)` writes into the durable queue |
| `catalog/__main__.py` | `python -m dispatch_library.catalog` — one process per command |
| `models.py` | Additive: candidate statuses, sources HUMAN/DISPATCH, lifecycle states, 18 object types, nine refused identities with normalisation, defaulted fields |
| `service.py` | `get_recipe`; `resolve_packet` accepts the string Publisher sends |

### Dispatch

`portal/models/library.py` (projection: catalog mode and legacy mode), `portal/routes/api.py`
(409 for edit/delete; placement fields), `dispatch/backup.py` (catalog snapshot, manifest, restore
mapping), `dispatch_launcher/settings.py`, `tests/conftest.py`, `tests/test_storage_routing.py`,
`tests/test_library_authority.py`.

### Joe-Assistant

`Workers/worker_bus/host.py`, `workers/library.py`, `workers/publisher.py`, their tests,
`Testing/phase_a_separate_processes.py`, `Testing/phase_a_steps.py`, `KNOWN_LIMITATIONS.md` §14,
`TEST_EVIDENCE.md` §10.

---

## 4. Tests

| Suite | Result |
|---|---|
| Library, all | **308 passed, 0 failed, 0 skipped** (JUnit), with `PUBLISHER_SRC` and `INTELLIGENCE_SRC` naming the real repositories |
| — schema | 128: the 99 refusals and 22 normal paths of plan §7.2, shape 19/4/34, parity of collections, identities and object types with Python |
| — concurrency | 5: WAL reader not blocked by a writer; busy writer fails clearly past its timeout; busy writer within its timeout waits and succeeds; two processes superseding one object 50 times with a third process reading throughout; two processes submitting 40 candidates |
| — integration | Publisher protocol signatures; `pull_libraries` across processes; REVIEW_DUE reaching Publisher as MISSING; Intelligence `route_to_library` into the durable queue, surviving restart, validated and approved in another process; field-for-field contract |
| — CLI | the full candidate and placement path, one process per step |
| Joe-Assistant Workers + Testing | **147 passed, 55 subtests passed, 0 skipped** |
| Dispatch, affected suites | **590 passed, 5 failed** — all 5 in `test_sandbox_survey.py`, failing identically on the unmodified branch (WinError 1314: symlink privilege; long path) |
| Dispatch, full suite | **4,197 passed, 38 failed** on `9669364` (41 min, clean environment). The 38 are in `test_launcher.py`, `test_rehearsal_and_proof.py`, `test_repository_doctrine.py`, `test_auth_lockout_concurrency.py`, `test_store_concurrency.py` and `test_sandbox_survey.py`. The same six files on the unmodified branch `4d247ac`: **37 failed**. The two tests that failed here but not in one baseline run were each repeated four times on both trees and failed in 2 of 4 runs on **both** — flaky on the original code. No failure is attributable to this build |

**Correction to plan v2 §7.2.** It said the nine-identity list "appears in six CHECKs". Six CHECKs
refuse system identities; four carry exactly the nine, the object-type confirmer carries the nine
plus `HUMAN`, and the notice resolver carries six. `test_every_refused_identity_list_is_the_python_constant`
pins the true shape.

---

## 5. Realistic runs on this machine

### 5.1 The production catalog

`D:\Dispatch Operations\Current Workspace\Library\catalog.db` — created clean (schema version 2,
WAL), each command its own process:

- `recipes-load D:\Library\publisher_recipes.json` → 2 recipes loaded, 3 placeholders.
- `scan` of `D:\Memory`, recorded as scan 1 → 18 folders, 16 files, 16 UNCATALOGUED, 0 CHANGED,
  0 MISSING, 6 UNMAPPED_FOLDER, 16 PLACEMENT_CONFLICT — exactly the approved mapping and conflicts.
- No document was placed or accepted: that needs Mike.

This is the only catalog on `D:`. Certification catalogs lived in scratchpad workspaces.

### 5.2 Backup and restore of the real catalog

Dispatch's own backup engine, every root sandboxed except `DISPATCH_LIBRARY_CATALOG`:
backup ok; manifest `schema_version 2`, `integrity_check ok`; no raw WAL in the archive;
`verify` all hashes match; restored into a scratch directory; **restored row counts equal the live
catalog in all 19 tables** (5 recipes, 27 requirements, 1 scan, 38 findings, 15 collections);
recipe and scan summary read back through the Library. The live catalog file's SHA-256 was
unchanged by the backup, and `C:\DispatchBackups` was not touched.

### 5.3 Publisher Phase A across separate processes

`Testing/phase_a_separate_processes.py`, final run on `6452f3b` / `9669364` / `cc03244`: passed
across 7 step processes and 2 CLI processes. Templates placed in one process were found by
`python -m worker_bus ask PUBLISHER check_readiness` in another ("Ready to assemble."); assembly
refused without authorisation and built with it; a REVIEW_DUE template blocked and renewed by a
named person; COMI withheld profit and margin; a system submitter refused; the `.eml` read back
from the workspace. Detail in Joe-Assistant `TEST_EVIDENCE.md` §10.

### 5.4 D:\Memory integrity

A SHA-256, size and modification-time listing of every entry under `D:\Memory` (19 directories,
16 files) was taken at the start of the session and compared after every step that could reach it,
including the production scan: **0 differences**. No shelf file was created, changed, moved,
renamed or deleted.

---

## 6. Stop conditions

| | Condition | Evidence |
|---|---|---|
| A | Library persists across real process restarts | CLI test (one process per step); contract suite across connections; production catalog built by five separate processes; Phase A §5.3 |
| B | Publisher retrieves persistent recipes and approved CURRENT assets | `pull_libraries` against the catalog in a fresh process; `get_recipe`; Phase A readiness and `current_for_external_use` as PUBLISHER; REVIEW_DUE blocked |
| C | Intelligence submits a durable candidate that survives restart | Real `dispatch_intel.service.route_to_library` into `DurableCandidateSink`; read back pending in a new process |
| D | Candidate validation and human decision end to end | Same candidate: Library validation fails without a confirmed type and raises notices; Intelligence confirms; validation passes; approved in a separate process; notices closed in the confirmer's name |
| E | Dispatch JSON Library contained | Catalog mode through the real Flask routes; no `library.json` in data dir or shelf; edit/delete 409; refusal when the Library is unimportable; legacy storage never in the shelf root |
| F | Backup and restore proven | Dispatch test on a live WAL catalog with the estate destroyed; §5.2 on the real catalog |
| G | Publisher Phase A across separate processes | §5.3 |
| H | D:\Memory unchanged except as Mike authorised | §5.4 |

---

## 7. Defects corrected, and workarounds used

| # | Found | Correction |
|---|---|---|
| 1 | Recipe reload re-versioned unchanged recipes (compared by file hash) | Compared per recipe |
| 2 | Two first placements of one object could race on the unique code | Object re-read under the write lock |
| 3 | A renewed asset kept its EXPIRED notice open | Renewal needs a person and closes the notice in their name |
| 4 | Publisher counted a present-but-blocked template as present | Only an answer carrying the asset counts |
| 5 | Portal JSON Library would write `library.json` into `D:\Memory` with the operator's environment | Legacy store in the portal data directory; refusal if that is the shelf |
| 6 | Portal reviewer identities lacked JOE, DISPATCH, COMI, EMAIL_HELPER and did not normalise | Nine, normalised |
| 7 | Candidate notices stayed open after the cause was cleared | Closed in the confirmer's name on validation |

Workarounds, all truthful and recorded:

- **Scratchpad worktrees** for Dispatch and Joe-Assistant, so the operator's working trees were not
  disturbed and no Dispatch copy was placed where the launcher's multi-copy scan looks.
- **Clean environment for every Dispatch-importing run** (`DISPATCH_*` and `PORTAL_*` dropped, then
  sandbox roots set), after the containment failure below.
- **`stdin=DEVNULL`** for child processes: without a console stdin, Windows `CreateProcess` failed
  with WinError 6 before the child ran.
- **Test identities** ("Certification Operator", "Phase A Certification Operator") for every
  approval in a kept catalog; "Mike Zachary" appears only inside disposable test databases.

### The containment failure

The first separate-process Phase A run inherited `DISPATCH_ARCHIVE_PATH=D:\Archive\CIN` from the
operator's user environment. The CIN outbox wrote one test message,
`D:\Archive\CIN\Outbox\completion-LOAD-20260913-C5B1AF82-ops@l1truck.com.eml` (442 bytes). An audit
of `D:\Archive`, `D:\Memory`, `D:\Dispatch Operations\Current Workspace` and `C:\DispatchBackups`
for the preceding three hours found that file and nothing else. It was moved — not deleted — into
that run's workspace, verified by hash, and every later run dropped all inherited Dispatch variables
and asserted that no configured path left the workspace. Nothing was delivered; SMTP was not
configured.

---

## 8. Blocked-work alerts — need Mike

> **Update — Alert 1 ported at Mike Zachary's direction.** `joe/capture-to-card` `8219962` carries the
> containment, including document upload (kept under the portal data directory; in catalog mode placed
> in the Library with person, type and SHA-256). Affected suites on that branch: 459 passed, 0 failed.
> Publisher Phase A passed across separate processes with that branch as Dispatch (Joe-Assistant
> `d5c6c10`). **Still Mike's:** `D:\Dispatch` is one commit behind its remote until pulled, and the
> Portal must be restarted to run it. `intelligence.py` and `driver_pin_registry.py` still write
> their own JSON stores into the memory root — not Library files, not changed.

**Alert 1 — the runtime Dispatch branch does not carry the containment**

| | |
|---|---|
| Worker | Library (containment of the Portal projection) |
| Blocked step | 11–12: contain the JSON Library and keep it out of the `D:\Memory` root on the Dispatch the laptop runs |
| Cause | `D:\Dispatch` runs `joe/capture-to-card`, which is not built on `sandbox/phase2-corrections` (18 / 118 commits apart). It also has `add_document`, which writes `LibraryDocuments` under `get_memory_dir()` — `D:\Memory` with this machine's environment |
| Impact | Until ported, the Portal on this laptop would write `library.json` and `LibraryDocuments` into `D:\Memory` the first time a Library record or document is added |
| Attempted | Implemented and tested on the assigned branch `9669364`; audited this machine — neither file exists in `D:\Memory` today |
| Workaround | None safe without choosing a branch: porting onto the runtime branch changes what the laptop runs |
| Recommended | Mike chooses the Dispatch line of record; the containment commit is then ported to it, including `add_document` / `documents_dir`, before the Portal next adds a Library record |
| Affected | `portal/models/library.py` on `joe/capture-to-card`; `D:\Memory` |

**Alert 2 — the catalog is not named in the operator's environment**

| | |
|---|---|
| Worker | Library |
| Blocked step | Portal and worker bus using the production catalog by default |
| Cause | `DISPATCH_LIBRARY_CATALOG` is unset. Setting a user environment variable is persistent system configuration, which needs Mike |
| Impact | Processes that are not told the path run the in-memory Library (worker bus) or legacy JSON (Portal) |
| Attempted | Production catalog created at the recommended path; every consumer reads the variable |
| Recommended | `setx DISPATCH_LIBRARY_CATALOG "D:\Dispatch Operations\Current Workspace\Library\catalog.db"`, and `DISPATCH_LIBRARY_SRC` to wherever the Library repository lives on the laptop |
| Affected | Portal, worker bus, backup |

**Alert 3 — a stale `cin_lite` install**

| | |
|---|---|
| Worker | Library (certification) |
| Cause | An editable install maps `cin_lite` to `C:\Documents\Level 1 build\Portal\cin-hybrid-main\cin_lite`, an old copy |
| Impact | A Python process without the Dispatch repository on its path imports that copy — the one-copy rule's failure mode |
| Workaround | Every run here put the Dispatch worktree first on `PYTHONPATH`; verified by `cin_lite.__file__` |
| Recommended | Mike decides whether to uninstall that editable package |

---

## 9. Remaining human and Microsoft actions

- **Mike:** alerts 1–3 above.
- **Mike:** accept real documents into the Library — nothing on the shelf is catalogued; 16 files
  wait, with their placement conflicts.
- **Mike:** decide the six unmapped folders; decide whether to catalogue the approved folder mapping
  as an Index manifest.
- **Mike:** Phase B — `DISPATCH_MS_TENANT`, `DISPATCH_MS_CLIENT_ID`, `DISPATCH_EMAIL_FROM`,
  `DISPATCH_TRANSPORT=graph`, device-code sign-in. **No email has been delivered by anything in
  this mission.**
- **Contracts document:** `DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md` (Claude-3 repository) still
  describes the pre-v2 candidate; the additive fields are recorded here and in `models.py`.
- **Dispatch's own pre-existing failures:** launcher, subprocess, symlink and multi-process tests
  fail on this machine on the unmodified branch too (§4). They are Dispatch's to fix and were not
  touched here.
