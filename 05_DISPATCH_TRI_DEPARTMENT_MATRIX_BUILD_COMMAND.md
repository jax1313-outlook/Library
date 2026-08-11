# 05_DISPATCH_TRI_DEPARTMENT_MATRIX_BUILD_COMMAND.md

Program: Dispatch
Owner: Mike Zachary / Level 1 Transport
Status: Build Command Draft
Purpose: Direct Claude Code to build Intell, Library, and Publisher as an integrated dependency chain, not as three isolated modules.
Rule: Integration-ready, merge-supporting, deployment-capable architecture. No automatic merge. No automatic deployment. Mike decides.

---

# 1. Mission

Build Intell, Library, and Publisher simultaneously as one dependency chain:

Intell
↓
Library
↓
Publisher

The goal is not three isolated repos with three isolated designs.

The goal is three departments that produce and consume compatible objects, use shared schemas/contracts, pass tests, and are ready for Claude Code review before merge into Dispatch.

---

# 2. Build Target

Build each department to:

- integration-ready status
- merge-ready candidate status
- deployment-capable architecture
- fully tested local operation
- clear service surfaces
- clear object ownership
- clear handoff contracts
- clear forbidden-path protections

Do not:

- auto-merge
- auto-deploy
- bypass Claude Code review
- bypass Mike approval
- treat build completion as production authorization

---

# 3. Required Source Inputs

Use these doctrine and source materials:

- DISPATCH_CONSTITUTION_v3.md
- DISPATCH_FINAL_BLUEPRINT_v1.md
- DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md
- DISPATCH_AGENT_RELATIONSHIP_MATRIX.md
- LIBRARY_INGESTION_RULE.md
- PUBLISHER.md
- INTELLIGENCE_ANALYST.md
- INTELLIGENCE_VERIFICATION_WORKFLOW.md
- Library Department Core Object Model
- Operational Memory Systems in Organizations
- Visibility SOP
- Publisher MVP prototype
- publisher_recipes.json
- Publisher templates
- Publisher Constitution Package
- Legacy Publisher Emails 1–5

If any source is missing from the repo, create a missing-source report and do not invent missing doctrine.

---

# 4. Department Build Requirements

## 4.1 Intell

Build Intell as the acquire-analyze-route function.

Intell must produce:

- Intelligence Finding
- Operational Consideration
- Special Requirement
- Publisher Requirement
- Library Candidate
- Manager Decision Support Note

Intell must not:

- approve findings as truth
- draft customer-facing documents
- submit outward-facing material
- decide pursuit
- alter scoring doctrine
- bypass Manager or Mike

## 4.2 Library

Build Library as current reusable truth and controlled production asset storage.

Library must provide:

- human-ingestion acceptance path
- object taxonomy
- current object resolver
- Publisher Parts collection
- Templates collection
- Company collection
- Broker collection
- Location Intelligence collection
- Route Intelligence collection
- Security sub-library placeholder if not already implemented

Library must not:

- create truth from Archive automatically
- force paper-tiger review loops on human-placed documents
- treat machine-generated findings as truth without approved path

## 4.3 Publisher

Build Publisher as a governed production assembly department.

Publisher must provide:

- recipe registry
- publisher request model
- readiness packet
- workspace model
- library pull logic
- parts inventory
- missing-item notice
- draft review package
- broker onboarding packet candidate
- government proposal package candidate
- visibility/evidence bundle candidate
- archive handoff package

Publisher must not:

- approve itself
- submit externally
- send emails automatically
- invent facts
- promote its outputs into Library truth without approval path
- bypass Manager or Mike

---

# 5. Required Shared Interface Contracts

Before coding department internals, define shared contracts for:

- Intelligence Finding
- Library Object
- Publisher Requirement
- Publisher Recipe
- Readiness Packet
- Parts Inventory
- Missing Item Notice
- Draft Review Package
- Archive Handoff Package
- Visibility Package
- POD / Evidence Bundle

Each object must define:

- owner
- fields
- source
- storage
- consumer
- review requirement
- approval requirement
- archive requirement
- tests

---

# 6. Build Matrix

| Build Unit | Owner | Depends On | Produces | Tests Required | Merge Ready When |
|---|---|---|---|---|---|
| Library Taxonomy | Library | System Relationship Matrix | collections/object classes | taxonomy tests | all collections resolve |
| Library Current Resolver | Library | Library Taxonomy | current object retrieval | current/superseded tests | stale objects excluded |
| Human Ingestion Acceptance | Library | Library Rule | accepted human documents | ingestion tests | no approval loop created |
| Intell Finding Model | Intell | Constitution/Intell Doctrine | finding object | source retention tests | no final decision allowed |
| Intell Publisher Requirement | Intell | Finding Model | publisher requirement object | handoff tests | Publisher can consume |
| Intell Library Candidate | Intell | Finding Model | library candidate object | candidate tests | Library can receive |
| Publisher Recipe Registry | Publisher | Library Resolver | recipe objects | recipe tests | recipes load and validate |
| Publisher Request | Publisher | Recipe Registry | request object | request tests | request creates valid flow |
| Readiness Packet | Publisher | Request + Recipe | readiness packet | packet tests | required items listed |
| Library Pull | Publisher | Library Resolver | pulled asset inventory | pull tests | missing items not invented |
| Parts Inventory | Publisher | Library Pull | present/missing list | inventory tests | gaps visible |
| Missing Item Notice | Publisher | Parts Inventory | draft notice | no-send tests | human review preserved |
| Draft Review Package | Publisher | Readiness Packet | review package | review gate tests | human review required |
| Archive Handoff Package | Publisher | Review Package | archive bundle | metadata tests | archive can receive |
| Visibility Package M1 | Publisher | Visibility SOP | status/POD/detention package | package tests | no external send path |

---

# 7. Required Test Categories

Each department must include tests for:

- ownership boundaries
- object creation
- retrieval correctness
- missing data behavior
- no-fabrication behavior
- no autonomous external action
- no self-approval
- Archive handoff integrity
- Manager/Portal readiness where applicable
- System Relationship Matrix compliance

---

# 8. Stop Conditions

Stop and create a Conflict Notice if:

- the build requires guessing an object schema
- the build requires inventing source material
- Publisher needs Library outputs that do not exist
- Publisher needs Intell outputs that do not exist
- Library needs approval doctrine not resolved by Library Ingestion Rule
- any function tries to bypass Manager or Mike
- any external send/submission path appears
- tests cannot prove no-fabrication behavior

---

# 9. Required Deliverables

Each repo must produce:

- README update
- architecture note
- object model
- service contract
- tests
- demo/walkthrough report
- merge readiness report
- known gaps list

Claude Code must produce a final cross-repo review package before any merge into Dispatch.

---

# 10. Final Rule

This command authorizes build-to-integration-ready status only.

It does not authorize:

- merge into Dispatch
- deployment
- production promotion
- external submission
- autonomous approval
- autonomous customer/broker/government communication

Mike decides.
