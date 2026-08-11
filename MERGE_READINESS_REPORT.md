# MERGE READINESS REPORT — Library

Program: Dispatch
Department: Library
Build: Tri-Department Matrix Build (Intelligence → Library → Publisher)
Date: 2026-08-11

---

## 1. Status

**Integration-ready candidate.** Not merged into Dispatch. Not deployed. Not production-promoted.
Per 07_DISPATCH_REPO_PLACEMENT_PLAN.md Section 3, this repo is at "Integration-ready candidate"
and awaits Claude Code cross-repo review, Hold/Test-Grounds, then Mike approval.

## 2. Required Outputs (Build Command Section 4.2 / 9)

| Required | Present |
|---|---|
| Object taxonomy | Yes — `src/dispatch_library/taxonomy.py`, 15 collections |
| Object registry | Yes — `src/dispatch_library/registry.py` |
| Current object resolver | Yes — `src/dispatch_library/resolver.py` |
| Human-ingestion acceptance path | Yes — `src/dispatch_library/ingestion.py::ingest_human_document` |
| Publisher Parts collection | Yes — `Publisher_Parts` in taxonomy; usable via `ingest_human_document`/candidates like any other collection |
| Templates / Company / Broker / Location_Intelligence collections | Yes — present in taxonomy, exercised in tests |
| Security sub-library placeholder | Present in taxonomy (`Security` collection); no additional Security-department integration exists in this repo (out of scope — Security is a separate department) |
| Service contracts | Yes — `src/dispatch_library/service.py` (`current`, `resolve_packet`, `submit_candidate`, `review_candidate`, `ingest_human_document`) |
| Tests | Yes — 24 tests, 24 passing |
| README | Yes |
| Merge readiness report | This document |

## 3. Test Summary

```
PYTHONPATH=src pytest -q
24 passed
```

Covers: current retrieval, version exclusion (superseded objects never returned), human-ingestion
acceptance with no approval loop, human-ingestion rejects system-identity `accepted_by`, candidate
lifecycle (PENDING_REVIEW → APPROVED/REJECTED), candidate self-approval blocked, double-review
blocked, recipe registration/supersession, recipe resolution reports MISSING rather than
fabricating, taxonomy completeness against the System Relationship Matrix.

## 4. Matrix Compliance Test (System Relationship Matrix Section 12)

| Question | Answer |
|---|---|
| What object is created? | `LibraryObject`, `LibraryCandidate`, `PublisherRecipe` |
| Who owns it? | Library |
| Where is it stored? | `ObjectRegistry` / `CandidateQueue` / `RecipeRegistry` (in-process reference stores) |
| Temporary, current truth, or history? | `LibraryObject` with `status=CURRENT` is truth; `SUPERSEDED` is history; `LibraryCandidate` is temporary until reviewed |
| Who consumes it? | Publisher, Manager, Portal, Intelligence |
| Who may not consume it? | Nothing bypasses `current()` — Publisher/Manager/Portal/Intelligence all read through the same resolver, so no consumer can see a non-current object by accident |
| Review requirement? | Yes for candidates; no additional loop for human-placed documents |
| Approval requirement? | Yes for candidates — external, non-self, enforced in code |
| Library candidate? | `LibraryCandidate` IS the candidate object |
| Archive requirement? | Superseded versions only (tracked via `status=SUPERSEDED`; actual Archive department write is out of scope, see Known Gaps) |
| Portal card? | Not created directly by this repo — Manager/Portal integration is out of scope here |
| Work item? | Not created directly by this repo |
| Test coverage? | Yes, see Section 3 |
| Forbidden path created? | None identified — see Section 5 |
| Reduces Mike's cognitive load? | Yes — one resolver call always returns current truth; no manual version tracking |

## 5. Hard Rule / Forbidden Path Verification

- Human-placed Library documents accepted per doctrine, no artificial validation loop: verified by `test_human_ingestion_is_immediately_current_no_second_gate`.
- Intelligence Finding -> Library Truth Automatically is forbidden: verified by `test_candidate_starts_pending_review_not_truth` and `test_candidate_cannot_approve_itself`.
- No authority bypass / no self-approval: verified by `test_candidate_cannot_approve_itself` (rejects both the submitting system's own identity and any reserved system identity).
- No fabrication in recipe resolution: verified by `test_resolve_packet_reports_missing_items_not_fabricated`.
- Archive is not current truth: no code path anywhere in this repo reads from an Archive source into `ObjectRegistry`.

## 6. Known Gaps

See `KNOWN_GAPS.md`.

## 7. Recommendation

This is a recommendation only. No merge, deployment, or promotion is authorized by this report.
Mike decides.
