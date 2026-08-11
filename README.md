# Dispatch Library

Library department implementation for the Dispatch program (Level 1 Transport / Mike Zachary).
This repo builds the **Library** link of the Intelligence → Library → Publisher dependency chain
defined in `04_DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md`.

> Legacy note: this repo was previously used as "Repo-3", a document-only package for assembling
> `DISPATCH_FINAL_BLUEPRINT_v1.md`. That mission is separate from this repo's current role.
> Per `07_DISPATCH_REPO_PLACEMENT_PLAN.md` ("Library Repo"), this repository's job is to build and
> test the Library department to integration-ready status. The governance documents mirrored at
> the repo root remain as load-bearing reference material; `src/` is new.

## Status

**Integration-ready candidate.** Not merged into Dispatch. Not deployed. Not production-promoted.
See `MERGE_READINESS_REPORT.md` and `KNOWN_GAPS.md`. Mike decides on promotion.

## What this repo does

`src/dispatch_library/` implements Library as current reusable truth and controlled production
asset storage (Constitution Section 7.4), never as temporary workspace or automatic truth from
Archive or Intelligence:

- **`taxonomy.py`** — the 15 Library collections (Constitution/Process/Operations/Compliance/
  Training/Reference/Templates/Company/Customer/Broker/Location_Intelligence/Route_Intelligence/
  Publisher_Parts/Security/Index), a closed set.
- **`models.py`** — `LibraryObject` (current truth), `LibraryCandidate` (pending nomination,
  field-compatible with the Intelligence repo's object of the same name), `PublisherRecipe`.
- **`registry.py`** — versioned Object Registry. Adding a new `CURRENT` version of an
  `object_code` automatically supersedes the previous one; at most one `CURRENT` version can
  exist per object_code at any time, by construction.
- **`resolver.py`** — `current(object_code)`, the read path every other department uses. Never
  returns a superseded or pending-review object.
- **`ingestion.py`** — the two acceptance paths into Library truth (see below).
- **`recipes.py`** — Publisher Recipe Registry + `resolve_packet()`, which resolves a recipe's
  required Library object codes against the registry and reports `MISSING` rather than
  fabricating a substitute.
- **`service.py`** — `LibraryService`, the single integration point bundling the above.

## Two acceptance paths (no artificial validation loop)

1. **Human-placed documents** (`ingest_human_document`) become `CURRENT` truth immediately.
   The placing human's identity (`accepted_by`) *is* the approval — there is no second review
   gate, per the Hard Rule "Human-placed Library documents are accepted per Library doctrine"
   and the Forbidden Movement "Human-Placed Library Asset -> Artificial Validation Loop".
2. **Machine-nominated candidates** (from Intelligence or Publisher, via `submit_candidate`)
   start `PENDING_REVIEW` and can only become truth through `review_candidate(..., approve=True,
   reviewed_by=<human>)`. `reviewed_by` can never be a system identity and can never equal the
   submitting department's own identity — enforced in code, not just by convention (Forbidden
   Movement: "Intelligence Finding -> Library Truth Automatically").

## Service surfaces

```python
from dispatch_library.service import LibraryService
from dispatch_library.models import RecipeType

library = LibraryService()
library.ingest_human_document("COI-TEMPLATE", "Templates", "COI Template", "...", "Mike Zachary")
obj = library.current("COI-TEMPLATE")
packet = library.resolve_packet(RecipeType.BROKER_ONBOARDING_PACKET)  # {code: obj | "MISSING"}
library.submit_candidate(candidate)                                   # PENDING_REVIEW
library.review_candidate(candidate.candidate_id, approve=True, reviewed_by="Mike Zachary")
```

## Install / Test

```bash
export PYTHONPATH=$(pwd)/src
pip install pytest
pytest -v
```

See `docs/OBJECT_MODEL.md` for the full schema reference.

## Boundaries (Constitution Section 7.4; Repo Placement Plan)

Library does not create truth from Archive automatically, does not force review loops on
human-placed documents, and does not treat machine-generated findings as truth without an
approved path. This repo contains no Publisher drafting logic, no Intelligence analysis logic,
and no Archive-history-as-current-truth logic.
