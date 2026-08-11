# KNOWN GAPS — Library

## Missing source material (Build Command Section 3)

Not found in any repo in scope: `LIBRARY_INGESTION_RULE.md`, "Library Department Core Object
Model" document, "Operational Memory Systems in Organizations", `publisher_recipes.json`. Content
was not invented — see `DISPATCH_SHARED_OBJECT_CONTRACTS_v1.md` Section 1 (Claude-3 repo) for the
full missing-source report. The human-ingestion behavior implemented here is derived directly
from `DISPATCH_CONSTITUTION_v3.md` Section 7.4 and the System Relationship Matrix's Hard Rules,
which were in hand — not from the missing `LIBRARY_INGESTION_RULE.md`. If that document surfaces
later and specifies different ingestion mechanics, this repo's `ingestion.py` should be reviewed
against it.

## Architectural gaps carried forward

- **No persistent store.** `ObjectRegistry`/`CandidateQueue`/`RecipeRegistry` are in-memory only.
  A Dispatch Spine-backed persistence layer is required before this integrates with a running
  Manager/Portal.
- **No live Archive integration.** Superseded objects are marked `SUPERSEDED` but nothing writes
  them to an actual Archive department (out of scope — Archive is a separate build, System
  Relationship Matrix Phase 4).
- **No Security sub-library implementation.** The `Security` collection exists in the taxonomy as
  required by Build Command Section 4.2 ("Security sub-library placeholder if not already
  implemented"), but no Security-department-specific behavior (credential handling, access
  control on Security-collection objects) is implemented — Security is a separate Dispatch
  department (Constitution Section 6.1/8) and out of scope for this build.
- **Recipe content is scaffold only.** `recipes.default_recipe_registry()` registers the five
  doctrine-named recipe types with empty `required_library_object_codes` lists. Real recipe
  content requires the missing `publisher_recipes.json` or equivalent Mike-approved source.
- **No Manager/Portal card generation.** Candidate review is a plain function call in this repo;
  a real integration would surface `pending_candidates()` as a Portal review card via
  Manager — that wiring is out of scope here (System Relationship Matrix ownership: Manager/
  Portal own card/work-item creation, not Library).

## Explicitly out of scope for this build

- Publisher drafting logic (Repo Placement Plan: "Should not contain").
- Intelligence analysis logic (Repo Placement Plan: "Should not contain").
- Archive history as current truth (Repo Placement Plan: "Should not contain").
- Artificial verification loops for human-placed documents (Repo Placement Plan: "Should not
  contain") — explicitly verified absent, see `MERGE_READINESS_REPORT.md` Section 5.
