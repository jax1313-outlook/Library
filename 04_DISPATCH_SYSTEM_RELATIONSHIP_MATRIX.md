# 04_DISPATCH_SYSTEM_RELATIONSHIP_MATRIX.md

Program: Dispatch
Owner: Mike Zachary / Level 1 Transport
Status: Source of Truth Candidate
Rule: No amendments. Rewrite and replace when doctrine changes.

---

# 1. Purpose

The Agent Relationship Matrix answers:

- Who may work with whom?
- Who may send?
- Who may receive?
- Who must escalate?
- What relationships are forbidden?

The System Relationship Matrix answers:

- What objects move?
- What produces them?
- What consumes them?
- Where are they stored?
- What services move them?
- What tests protect them?
- What build dependencies exist?

Agent Relationship Matrix = Authority

System Relationship Matrix = Implementation Dependency

---

# 2. Dispatch Top-To-Bottom Dependency Chain

Intelligence
↓
Library
↓
Publisher
↓
Archive
↓
Manager
↓
Portal
↓
Human Authority

Cross-Cutting Systems:

- Spine
- Security
- Alert Governance
- Versioning
- Audit

Dispatch is not a step-action program.

Dispatch is a dependency chain.

No department may be built independently if another department depends upon its outputs.

---

# 3. System Layer Ownership

## Authority

Owns:
- Final decisions
- Approvals
- Constitution changes
- Permanent architecture changes

Does Not Own:
- Draft creation
- Data routing
- Intelligence gathering

## Portal

Owns:
- Human display
- Review surfaces
- Action surfaces

Does Not Own:
- Truth
- Records
- Decisions

## Manager

Owns:
- Priority
- Routing
- Attention management
- Escalation preparation

Does Not Own:
- Final approval
- Commitment
- Submission

## Spine

Owns:
- Work items
- Events
- Portal cards
- Audit events
- State transitions

Does Not Own:
- Business interpretation

## Security

Owns:
- PIN
- Identity
- Role
- Session
- Access

Does Not Own:
- Business approval

## Intelligence

Owns:
- Analysis
- Findings
- Requirements
- Risk interpretation

Does Not Own:
- Current truth
- External deliverables

## Library

Owns:
- Current reusable truth
- Controlled assets
- Templates
- Production components

Does Not Own:
- History
- Drafts
- Archive evidence

## Publisher

Owns:
- Packages
- Drafts
- Deliverables
- Visibility outputs
- Evidence bundles

Does Not Own:
- Approval
- Truth promotion
- Fact invention

## Archive

Owns:
- Completed records
- Evidence
- Audit history
- Retention

Does Not Own:
- Current truth

---

# 4. Department Dependency Matrix

## INTELLIGENCE

Consumes:
- Source data
- Processing results
- Approved Library knowledge

Produces:
- Intelligence Findings
- Operational Considerations
- Special Requirements
- Library Candidates
- Publisher Requirements
- Decision Support

Feeds:
- Library
- Publisher
- Manager

Build Dependency:
Must exist before Library intelligence objects.

---

## LIBRARY

Consumes:
- Human-placed assets
- Approved doctrine
- Approved intelligence
- Approved reusable Publisher assets

Produces:
- Current Truth
- Templates
- Credentials
- Publisher Parts
- Intelligence Summaries
- Retrieval Responses

Feeds:
- Publisher
- Intelligence
- Manager
- Portal

Build Dependency:
Must exist before Publisher.

---

## PUBLISHER

Consumes:
- Library objects
- Templates
- Publisher Parts
- Intelligence requirements
- Human inputs

Produces:
- Readiness Packets
- Review Packages
- Missing Item Notices
- Proposal Packages
- Broker Packets
- Visibility Packages
- POD Packages
- Evidence Bundles
- Archive Handoffs

Feeds:
- Archive
- Manager
- Portal
- Human

Build Dependency:
Requires Library and Intelligence.

---

## ARCHIVE

Consumes:
- Final products
- Approval records
- Source evidence
- Completion packages

Produces:
- Archive Records
- Retrieval References
- Audit Bundles
- Retention Notices

Feeds:
- Manager
- Portal
- Library Review Candidates

Build Dependency:
Requires Publisher outputs.

---

## MANAGER

Consumes:
- Findings
- Status
- Alerts
- Work items
- Package status
- Archive signals

Produces:
- Routing
- Review cards
- Staff reports
- Decision support

Feeds:
- Portal
- Human

---

## PORTAL

Consumes:
- Cards
- Reviews
- Status
- Visibility outputs

Produces:
- Human action events
- Approval requests

Feeds:
- Spine
- Manager

---

# 5. Object Movement Matrix

## Intelligence Finding

Created By:
Intelligence

Stored In:
Intelligence Store
Archive Reference

Consumed By:
Manager
Library Candidate
Publisher

Library Truth?
No

Archive Required?
Yes

---

## Operational Consideration

Created By:
Intelligence

Consumed By:
Manager
Publisher

Library Truth?
Candidate Only

---

## Library Object

Created By:
Library

Consumed By:
Publisher
Manager
Portal
Intelligence

Library Truth?
Yes

Archive Required?
Superseded Versions Only

---

## Publisher Recipe

Created By:
Library / Publisher Parts

Consumed By:
Publisher

Library Truth?
Yes

Archive Required?
Version Archive

---

## Readiness Packet

Created By:
Publisher

Consumed By:
Publisher
Manager
Human

Library Truth?
No

Archive Required?
Yes

---

## Parts Inventory

Created By:
Publisher

Consumed By:
Publisher
Manager
Human

Library Truth?
No

Archive Required?
Yes

---

## Missing Item Notice

Created By:
Publisher

Consumed By:
Human
Manager

Library Truth?
No

Archive Required?
Optional

---

## Review Package

Created By:
Publisher

Consumed By:
Human
Manager
Portal

Library Truth?
No

Archive Required?
Yes

---

## Visibility Package

Created By:
Publisher

Consumed By:
Customer
Broker
Manager
Portal

Library Truth?
Template Only

Archive Required?
Yes

---

## POD Package

Created By:
Publisher

Consumed By:
Customer
Broker
Archive

Library Truth?
Template Only

Archive Required?
Yes

---

## Approval Event

Created By:
Portal
Spine

Consumed By:
Archive
Manager

Archive Required?
Always

---

## Audit Event

Created By:
Spine
Security

Consumed By:
Archive

Archive Required?
Always

---

# 6. Intell → Library → Publisher Chain

INTELLIGENCE OUTPUTS

- Findings
- Operational Considerations
- Special Requirements
- Publisher Requirements
- Library Candidates
- Decision Support Notes

↓

LIBRARY OBJECTS

- Intelligence Summaries
- Location Intelligence
- Broker Intelligence
- Route Intelligence
- SOP Candidates
- Reference Objects
- Templates
- Publisher Parts

↓

PUBLISHER INPUTS

- Intelligence Requirements
- Intelligence Summaries
- Company Assets
- Credentials
- Templates
- Publisher Parts

↓

PUBLISHER OUTPUTS

- Government Packages
- Broker Packets
- Visibility Packages
- Evidence Bundles
- POD Packages
- Review Packages

↓

ARCHIVE

- Completed Record
- Evidence
- Audit Bundle
- Retention Package

---

# 7. Library Collections

- Constitution
- Process
- Operations
- Compliance
- Training
- Reference
- Templates
- Company
- Customer
- Broker
- Location_Intelligence
- Route_Intelligence
- Publisher_Parts
- Security
- Index

---

# 8. Required Service Surfaces

- library.current(object_code)
- library.resolve_packet(recipe_type)
- library.submit_candidate(candidate)
- publisher.create_request()
- publisher.create_readiness_packet()
- publisher.pull_libraries()
- publisher.create_inventory()
- publisher.create_missing_notice()
- publisher.create_review_package()
- intell.create_finding()
- intell.route_to_publisher()
- intell.route_to_library()
- archive.create_bundle()
- manager.surface_card()
- spine.create_work_item()
- spine.create_portal_card()

---

# 9. Test Dependency Matrix

## Library

- Current retrieval
- Version exclusion
- Human-ingestion acceptance

## Publisher

- Recipe resolution
- Readiness packet
- Parts inventory
- Missing-item notice
- No-fabrication behavior
- Human review enforcement

## Intelligence

- Source retention
- Finding creation
- Requirement routing
- No final decision behavior

## Archive

- Bundle creation
- Retention assignment
- Evidence preservation

## Manager

- Review cards
- Routing cards
- Alert display

## Portal

- Review display
- Approval display

## Security

- Identity
- Session
- Permission

---

# 10. Build Order Matrix

## PHASE 0

- Source Import
- Reconciliation
- System Relationship Matrix

## PHASE 1

Library Foundation

- Taxonomy
- Registry
- Current Resolver
- Human Ingestion Path
- Publisher Parts

## PHASE 2

Intelligence Foundation

- Finding Schema
- Requirement Handoff
- Library Candidate Handoff
- Decision Support

## PHASE 3

Publisher Foundation

- Recipe Registry
- Request Model
- Readiness Packet
- Workspace
- Library Pull
- Inventory
- Missing Item Notice
- Review Package

## PHASE 4

Archive

- Archive Bundle
- Retention
- POD Package
- Visibility Package

## PHASE 5

Manager + Portal

- Review Cards
- Status Cards
- Publisher Review Screens

## PHASE 6

Security + Authority

- Approval Events
- Session Proof Chain
- Role Verification
- External Action Controls

---

# 11. Forbidden System Movements

Publisher -> Library Truth
WITHOUT approval path

Intelligence Finding -> Library Truth
Automatically

Archive Record -> Library Truth
Automatically

Publisher -> External Send
WITHOUT approval

Manager -> Final Approval

Portal -> System Of Record

Security -> Business Decision

Any Agent -> Mike Bypass

Human-Placed Library Asset
-> Artificial Validation Loop

Semantic Layer
-> Source Of Truth

---

# 12. Matrix Compliance Test

Every build must answer:

1. What object is created?
2. Who owns it?
3. Where is it stored?
4. Is it temporary, current truth, or history?
5. Who consumes it?
6. Who may not consume it?
7. Does it require review?
8. Does it require approval?
9. Does it become a Library candidate?
10. Does it require Archive preservation?
11. Does it create a Portal card?
12. Does it create a Work Item?
13. What test validates it?
14. What forbidden path can it create?
15. Does it reduce Mike's cognitive load?

If any answer is unknown:

STOP.

Produce Conflict Notice.

---

# 13. Final Rule

Agent Relationship Matrix
=
Who May Work Together

System Relationship Matrix
=
What Moves Through The System

Neither authorizes implementation.

Build Sequence:

Spec
↓
Prompt
↓
Build
↓
Test
↓
Review
↓
Approval

Mike Decides.
