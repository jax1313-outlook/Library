# OBJECT MODEL

Canonical source: `DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md` in the Claude-3 repo, Sections 3.5 and
4. This page documents this repo's implementation (`src/dispatch_library/models.py`).

## LibraryObject

| Field | Notes |
|---|---|
| `object_code` | stable key; multiple versions share the same code |
| `collection` | must be one of the 15 taxonomy collections — constructor raises `ValueError` otherwise |
| `version` | monotonically increasing per `object_code`, assigned by `registry.next_version()` |
| `status` | `CURRENT` \| `SUPERSEDED` \| `DRAFT_CANDIDATE` — at most one `CURRENT` per `object_code` |
| `source` | `HUMAN_PLACED` \| `APPROVED_CANDIDATE` — how this version entered Library truth |
| `accepted_by` | required; constructor rejects system identities (`INTELLIGENCE`, `PUBLISHER`, `LIBRARY`, `SYSTEM`, `AUTOMATION`) — a real human or approved-workflow name is required |
| `supersedes_version` | set automatically by the ingestion helpers |

## LibraryCandidate

Field-identical to the Intelligence repo's `LibraryCandidate` (same names, same enum values) —
this is what makes a candidate object produced by `dispatch_intel.service.route_to_library()`
directly constructible here without translation. `status` starts `PENDING_REVIEW` and only
`ingestion.review_candidate()` can change it, and only with an external `reviewed_by`.

## PublisherRecipe

`recipe_type` is one of five doctrine-named types (`docs/OBJECT_MODEL.md` cross-reference:
`DISPATCH_CONSTITUTION_v3.md` Section 7.2/7.7, `PUBLISHER.md` Sections 2/4).
`required_library_object_codes` content is `SCAFFOLD — PENDING REAL SOURCE`
(`publisher_recipes.json` was not found in any repo in scope) — see `KNOWN_GAPS.md`.

## Storage

`registry.ObjectRegistry` is an in-memory reference store for local/test use, mirroring the same
integration-boundary posture as the Intelligence repo's `IntelligenceStore`: a Dispatch
Spine-backed persistence layer would implement the same `add_version`/`history`/`get_version`
surface. `ingestion.CandidateQueue` is the Library Candidate Queue referenced throughout the
System Relationship Matrix and Agent Relationship Matrix.
