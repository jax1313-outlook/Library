"""Catalog behaviour: placement, candidates, notices, lifecycle, recipes, and the shelf."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from dispatch_library.catalog import CatalogRefusal, MissingObjectType, open_library
from dispatch_library.models import LibraryCandidate, RESERVED_SYSTEM_IDENTITIES, SubmittedBy
from test_recipes import SAMPLE

PERSON = "Certification Operator"
REAL_MEMORY = Path(os.environ.get("DISPATCH_MEMORY_ROOT_FOR_TESTS", r"D:\Memory"))


@pytest.fixture
def shelf(tmp_path):
    root = tmp_path / "Memory"
    (root / "Templates").mkdir(parents=True)
    (root / "Company Library" / "Agent Worker Constitutions").mkdir(parents=True)
    (root / "Fuel").mkdir()
    (root / "Templates" / "closeout.md").write_text("Closeout {load_id}", encoding="utf-8")
    (root / "Company Library" / "Agent Worker Constitutions" / "README.md").write_text("constitutions", encoding="utf-8")
    return root


@pytest.fixture
def lib(tmp_path, shelf):
    service = open_library(tmp_path / "catalog.db", memory_root=shelf, consumer_role="PUBLISHER")
    yield service
    service.close()


def _place(lib, code="TPL-BROKER-CLOSEOUT", **kw):
    args = dict(object_type="FORM_TEMPLATE")
    args.update(kw)
    return lib.ingest_human_document(code, "Templates", "Broker closeout", kw.pop("body", "body"), PERSON, **args)


def _intel_candidate(code="CAND-0badc0de"):
    return LibraryCandidate(
        submitted_by=SubmittedBy.INTELLIGENCE, source_type="Load board opportunity", collection="Reference",
        proposed_object_code=code, proposed_title="Dedicated route", proposed_body_or_reference="pointer to finding",
        source_finding_id="finding-0badc0de")


# ── placement ────────────────────────────────────────────────────────────

class TestHumanPlacement:
    def test_direct_acceptance_needs_no_second_gate(self, lib):
        obj = _place(lib)
        assert (obj.lifecycle_state, obj.accepted_by, obj.source.value, obj.version_label) == (
            "CURRENT", PERSON, "HUMAN_PLACED", "1.0")
        approvals = lib.connection.execute("SELECT approval_basis, approval_status FROM approval_record").fetchall()
        assert [tuple(r) for r in approvals] == [("HUMAN_PLACED", "APPROVED")]
        assert lib.pending_candidates() == []

    def test_missing_object_type_is_refused_and_recorded(self, lib):
        with pytest.raises(MissingObjectType) as refused:
            lib.place_file("LIB-TEMPLATES-FORM-CLOSEOUT", "Templates", "Closeout", "Templates/closeout.md", PERSON)
        notice = lib.catalog.notices()[0]
        assert (notice["notice_id"], notice["notice_type"], notice["missing_field"], notice["relative_path"]) == (
            refused.value.notice_id, "MISSING_FIELD", "object_type", "Templates/closeout.md")
        assert lib.list_current() == []

    def test_the_same_refusal_twice_is_one_notice(self, lib):
        for _ in range(2):
            with pytest.raises(MissingObjectType):
                lib.ingest_human_document("TPL-X", "Templates", "x", "x", PERSON)
        assert len(lib.catalog.notices()) == 1

    def test_type_is_never_inferred_from_collection(self, lib):
        with pytest.raises(MissingObjectType):
            lib.ingest_human_document("TPL-X", "Templates", "x", "x", PERSON)

    @pytest.mark.parametrize("who", sorted(RESERVED_SYSTEM_IDENTITIES) + ["Joe", "email helper", "Email-Helper", " comi "])
    def test_every_prohibited_system_approver_is_refused(self, lib, who):
        with pytest.raises(CatalogRefusal, match="system identity"):
            _place(lib, accepted_by=who) if False else lib.ingest_human_document(
                "TPL-1", "Templates", "t", "b", who, object_type="FORM_TEMPLATE")
        assert lib.list_current() == []

    def test_joe_is_the_capture_channel_never_the_approver(self, lib):
        obj = lib.ingest_human_document("TPL-1", "Templates", "t", "b", "Mike Zachary", object_type="FORM_TEMPLATE",
                                        capture_channel="JOE", capture_ref="joe-capture-1")
        assert (obj.accepted_by, obj.capture_channel) == ("Mike Zachary", "JOE")
        with pytest.raises(CatalogRefusal):
            lib.ingest_human_document("TPL-2", "Templates", "t", "b", "JOE", object_type="FORM_TEMPLATE",
                                      capture_channel="JOE")

    def test_a_person_named_joe_smith_is_a_person(self, lib):
        assert _place(lib, code="TPL-2").accepted_by == PERSON
        assert lib.ingest_human_document("TPL-3", "Templates", "t", "b", "Joe Smith",
                                         object_type="FORM_TEMPLATE").accepted_by == "Joe Smith"

    def test_type_and_collection_are_identity(self, lib):
        _place(lib)
        with pytest.raises(CatalogRefusal, match="different type"):
            lib.ingest_human_document("TPL-BROKER-CLOSEOUT", "Templates", "t", "b", PERSON, object_type="PACKET")
        with pytest.raises(CatalogRefusal, match="moving collection"):
            lib.ingest_human_document("TPL-BROKER-CLOSEOUT", "Reference", "t", "b", PERSON, object_type="FORM_TEMPLATE")


class TestVersionsAndSupersession:
    def test_major_and_minor(self, lib):
        _place(lib)
        assert lib.ingest_human_document("TPL-BROKER-CLOSEOUT", "Templates", "t", "typo fix", PERSON, minor=True).version_label == "1.1"
        assert _place(lib).version_label == "2.0"
        states = [(o.version_label, o.lifecycle_state) for o in lib.history("TPL-BROKER-CLOSEOUT")]
        assert states == [("1.0", "SUPERSEDED"), ("1.1", "SUPERSEDED"), ("2.0", "CURRENT")]

    def test_current_plus_three_are_retained_older_queue_for_review(self, lib):
        for _ in range(6):
            _place(lib)
        queued = [(r["version_major"], r["disposition"]) for r in lib.catalog.retention_queue()]
        assert queued == [(1, "PENDING"), (2, "PENDING")]
        assert lib.catalog.counts()["library_version"] == 6, "nothing is deleted"

    def test_archive_and_retention_decision_by_a_person(self, lib):
        for _ in range(5):
            _place(lib)
        v1 = lib.catalog.version_rows("TPL-BROKER-CLOSEOUT")[0]
        lib.catalog.archive_version(v1["version_id"], "ARC-2026-0913-0001")
        with pytest.raises(CatalogRefusal):
            lib.catalog.decide_retention(v1["version_id"], "DELETE", "AUTOMATION")
        decided = lib.catalog.decide_retention(v1["version_id"], "KEEP", PERSON)
        assert (decided["disposition"], decided["decided_by"]) == ("KEEP", PERSON)
        assert lib.catalog.version_row(v1["version_id"])["lifecycle_state"] == "RETENTION_REVIEW"


class TestExternalUse:
    def test_review_due_is_blocked_from_external_use_and_resolve_packet(self, tmp_path, lib):
        recipes = tmp_path / "recipes.json"
        recipes.write_text(json.dumps(SAMPLE), encoding="utf-8")
        lib.load_recipes(recipes)
        lib.ingest_human_document("w9", "Company", "W-9", "W-9 on file", PERSON, object_type="COMPANY_CREDENTIAL")
        assert lib.resolve_packet("BROKER_ONBOARDING_PACKET")["w9"] != "MISSING"
        lib.set_lifecycle("w9", "REVIEW_DUE")
        assert lib.current_for_external_use("w9") is None
        assert lib.current("w9").lifecycle_state == "REVIEW_DUE"
        assert lib.resolve_packet("BROKER_ONBOARDING_PACKET")["w9"] == "MISSING"
        assert lib.resolve_packet_detail("BROKER_ONBOARDING_PACKET")["w9"]["outcome"] == "BLOCKED_REVIEW_DUE"
        assert lib.catalog.notices(notice_type="EXPIRED")[0]["status"] == "OPEN"
        outcomes = [r["outcome"] for r in lib.catalog.retrieval_events("w9")]
        assert "BLOCKED_REVIEW_DUE" in outcomes

    def test_renewal_is_a_persons_act_and_closes_the_expired_notice(self, lib):
        lib.ingest_human_document("coi", "Company", "COI", "certificate", PERSON, object_type="COMPANY_CREDENTIAL")
        lib.set_lifecycle("coi", "REVIEW_DUE")
        with pytest.raises(CatalogRefusal, match="a renewal must name a real person"):
            lib.set_lifecycle("coi", "CURRENT")
        with pytest.raises(CatalogRefusal):
            lib.set_lifecycle("coi", "CURRENT", by="JOE")
        lib.set_lifecycle("coi", "CURRENT", by="Mike Zachary")
        notice = lib.catalog.notices(status=None, notice_type="EXPIRED")[0]
        assert (notice["status"], notice["resolved_by"]) == ("RESOLVED", "Mike Zachary")
        assert lib.current_for_external_use("coi") is not None

    def test_review_due_date_sweep(self, lib):
        lib.ingest_human_document("coi", "Company", "COI", "certificate", PERSON, object_type="COMPANY_CREDENTIAL",
                                  review_due_date="2026-01-01")
        assert lib.catalog.mark_review_due("2026-09-13") == ["coi"]
        assert lib.current("coi").lifecycle_state == "REVIEW_DUE"


# ── candidates ───────────────────────────────────────────────────────────

class TestCandidates:
    def test_intelligence_candidate_full_path(self, lib):
        c = lib.submit_candidate(_intel_candidate())
        assert c.status.value == "PENDING_REVIEW"
        with pytest.raises(CatalogRefusal, match="validated by Library"):
            lib.review_candidate(c.candidate_id, True, PERSON)
        failed = lib.validate_candidate(c.candidate_id)
        assert not failed["passed"]
        kinds = sorted(n["notice_type"] for n in lib.catalog.notices())
        assert kinds == ["BLOCKED_WORK", "MISSING_FIELD"]
        lib.classify_candidate(c.candidate_id, "VALIDATED_INTELLIGENCE_SUMMARY")
        assert lib.candidate(c.candidate_id).proposed_object_type is None, "a recommendation confirms nothing"
        with pytest.raises(CatalogRefusal):
            lib.confirm_object_type(c.candidate_id, "VALIDATED_INTELLIGENCE_SUMMARY", "Library")
        lib.confirm_object_type(c.candidate_id, "VALIDATED_INTELLIGENCE_SUMMARY", "Intelligence")
        assert lib.validate_candidate(c.candidate_id)["passed"]
        assert all(n["status"] == "RESOLVED" for n in lib.catalog.notices(status=None))
        decided = lib.review_candidate(c.candidate_id, True, "Mike Zachary", capture_channel="JOE")
        assert decided.status.value == "APPROVED"
        obj = lib.current("CAND-0badc0de")
        assert (obj.source.value, obj.accepted_by, obj.capture_channel, obj.object_type) == (
            "APPROVED_CANDIDATE", "Mike Zachary", "JOE", "VALIDATED_INTELLIGENCE_SUMMARY")

    def test_library_may_not_nominate(self, lib):
        with pytest.raises(CatalogRefusal, match="Library may not nominate"):
            lib.catalog.submit_candidate(submitted_by_role="LIBRARY", source_type="scan", collection="Reference",
                                         proposed_object_code="X", proposed_title="x", proposed_body_or_reference="x")

    def test_dispatch_needs_a_mission_record_or_workflow_event(self, lib):
        base = dict(submitted_by_role="DISPATCH", source_type="POD upload", collection="Location_Intelligence",
                    proposed_object_code="LOC-1", proposed_title="Dock 7", proposed_body_or_reference="gate code")
        with pytest.raises(CatalogRefusal, match="Mission Record"):
            lib.catalog.submit_candidate(**base)
        assert lib.catalog.submit_candidate(**base, mission_record_id="MR-LOAD-0001")["status"] == "PENDING_REVIEW"

    def test_a_human_candidate_carries_a_human_name(self, lib):
        base = dict(submitted_by_role="HUMAN", source_type="note", collection="Reference",
                    proposed_object_code="REF-1", proposed_title="x", proposed_body_or_reference="x")
        with pytest.raises(CatalogRefusal):
            lib.catalog.submit_candidate(**base)
        with pytest.raises(CatalogRefusal):
            lib.catalog.submit_candidate(**base, submitted_by_name="Joe")
        row = lib.catalog.submit_candidate(**base, submitted_by_name="Mike Zachary", proposed_object_type="CONTROLLED_COMPANY_FACT")
        assert row["object_type_confirmed_by"] == "Mike Zachary"

    def test_reject_and_defer_are_recorded_decisions(self, lib):
        c = lib.submit_candidate(_intel_candidate())
        deferred = lib.defer_candidate(c.candidate_id, "Mike Zachary", "after the load closes")
        assert deferred.status.value == "DEFERRED"
        lib.catalog.resubmit_deferred(c.candidate_id)
        rejected = lib.review_candidate(c.candidate_id, False, "Mike Zachary")
        assert rejected.status.value == "REJECTED"
        decisions = [r["approval_status"] for r in lib.connection.execute(
            "SELECT approval_status FROM approval_record WHERE candidate_id = ? ORDER BY approved_at", (c.candidate_id,))]
        assert decisions == ["DEFERRED", "REJECTED"]

    def test_candidates_survive_the_process(self, tmp_path, shelf):
        path = tmp_path / "durable.db"
        first = open_library(path, memory_root=shelf)
        cid = first.submit_candidate(_intel_candidate()).candidate_id
        first.close()
        second = open_library(path, memory_root=shelf)
        assert [c.candidate_id for c in second.pending_candidates()] == [cid]
        second.close()

    def test_a_foreign_intelligence_dataclass_crosses_unchanged(self, lib):
        """A stand-in with exactly the twelve fields of dispatch_intel.models.LibraryCandidate."""
        import dataclasses
        from enum import Enum

        class IntelSubmittedBy(str, Enum):
            INTELLIGENCE = "INTELLIGENCE"
            PUBLISHER = "PUBLISHER"

        class IntelStatus(str, Enum):
            PENDING_REVIEW = "PENDING_REVIEW"

        @dataclasses.dataclass
        class IntelCandidate:
            submitted_by: IntelSubmittedBy
            source_type: str
            collection: str
            proposed_object_code: str
            proposed_title: str
            proposed_body_or_reference: str
            source_finding_id: str = None
            status: IntelStatus = IntelStatus.PENDING_REVIEW
            reviewed_by: str = None
            reviewed_at: str = None
            candidate_id: str = "c0ffee00-0000-4000-8000-000000000001"
            created_at: str = "2026-09-13T20:00:00+00:00"

        foreign = IntelCandidate(IntelSubmittedBy.INTELLIGENCE, "Load board opportunity", "Reference",
                                 "CAND-c0ffee00", "Title", "pointer", "finding-c0ffee00")
        received = lib.submit_candidate(foreign)
        assert (received.candidate_id, received.created_at, received.source_finding_id) == (
            foreign.candidate_id, foreign.created_at, "finding-c0ffee00")
        refs = [r["ref_kind"] for r in lib.catalog.source_refs(candidate_id=foreign.candidate_id)]
        assert refs == ["INTELLIGENCE_FINDING"]


class TestNotices:
    def test_library_raises_and_a_person_or_source_resolves(self, lib):
        notice_id = lib.catalog.raise_notice("CONFLICT", relative_path="Company/w9.pdf", detail="two copies")
        for who in ("Library", "JOE", "automation", "Email Helper"):
            with pytest.raises(CatalogRefusal):
                lib.resolve_notice(notice_id, who, "done")
        resolved = lib.resolve_notice(notice_id, "Publisher", "newer copy nominated")
        assert (resolved["status"], resolved["resolved_by"]) == ("RESOLVED", "Publisher")


class TestRecordsBesideObjects:
    def test_metadata_sources_relationships_archive_links(self, lib):
        _place(lib)
        lib.ingest_human_document("w9", "Company", "W-9", "W-9", PERSON, object_type="COMPANY_CREDENTIAL")
        lib.catalog.set_metadata("w9", "issuing_authority", "IRS")
        lib.catalog.set_metadata("w9", "expiration_date", "2027-01-01", "DATE", version_bound=True)
        lib.catalog.set_metadata("w9", "issuing_authority", "Internal Revenue Service")
        assert lib.catalog.metadata("w9") == {"issuing_authority": "Internal Revenue Service", "expiration_date": "2027-01-01"}
        lib.catalog.relate("TPL-BROKER-CLOSEOUT", "w9", "DEPENDS_ON")
        assert [tuple(r)[:3] for r in lib.catalog.relationships("w9")] == [("DEPENDS_ON", "TPL-BROKER-CLOSEOUT", "w9")]
        lib.catalog.link_archive("w9", "ARC-EVIDENCE-1", "SOURCE_EVIDENCE", description="scanned original")
        version_id = lib.catalog.current_row("w9")["current_version_id"]
        lib.catalog.add_source_ref("EXTERNAL_DOCUMENT", "IRS W-9 Rev. 2024", version_id=version_id)
        assert [r["ref_kind"] for r in lib.catalog.source_refs(version_id=version_id)] == ["EXTERNAL_DOCUMENT"]


# ── recipes ──────────────────────────────────────────────────────────────

class TestRecipes:
    def test_persist_idempotent_supersede_and_placeholders(self, tmp_path, shelf):
        path = tmp_path / "catalog.db"
        recipes = tmp_path / "publisher_recipes.json"
        recipes.write_text(json.dumps(SAMPLE), encoding="utf-8")
        lib = open_library(path, memory_root=shelf)
        first = lib.load_recipes(recipes)
        assert sorted(first["loaded"]) == ["BROKER_ONBOARDING_PACKET", "GOVERNMENT_PROPOSAL_PACKET"]
        assert sorted(first["placeholders"]) == ["POD_PACKAGE", "REVIEW_PACKAGE", "VISIBILITY_STATUS_PACKET"]
        lib.close()

        lib = open_library(path, memory_root=shelf)
        assert sorted(lib.load_recipes(recipes)["unchanged"]) == ["BROKER_ONBOARDING_PACKET", "GOVERNMENT_PROPOSAL_PACKET"]
        recipe = lib.get_recipe("BROKER_ONBOARDING_PACKET")
        source = SAMPLE["broker_onboarding"]
        assert recipe["required_library_object_codes"] == source["required_company_items"]
        assert recipe["required_publisher_parts"] == source["required_publisher_items"]
        assert recipe["required_human_items"] == source["required_human_items"]
        assert recipe["required_outputs"] == source["required_outputs"]
        assert recipe["human_review_required"] is True
        assert lib.get_recipe("POD_PACKAGE")["is_placeholder"] is True

        changed = dict(SAMPLE)
        changed["broker_onboarding"] = dict(SAMPLE["broker_onboarding"], required_outputs=["draft_broker_packet"])
        recipes.write_text(json.dumps(changed), encoding="utf-8")
        assert lib.load_recipes(recipes)["loaded"] == ["BROKER_ONBOARDING_PACKET"]
        assert lib.get_recipe("BROKER_ONBOARDING_PACKET")["version"] == 2
        lib.close()

    @pytest.mark.skipif(not Path(r"D:\Library\publisher_recipes.json").is_file(), reason="real recipes not on this machine")
    def test_the_real_file(self, lib):
        real = Path(r"D:\Library\publisher_recipes.json")
        before = hashlib.sha256(real.read_bytes()).hexdigest()
        lib.load_recipes(real)
        assert lib.get_recipe("GOVERNMENT_PROPOSAL_PACKET")["source_sha256"] == before
        assert hashlib.sha256(real.read_bytes()).hexdigest() == before


# ── the shelf ────────────────────────────────────────────────────────────

def _listing(root: Path):
    return sorted((p.relative_to(root).as_posix(), p.stat().st_size, p.stat().st_mtime_ns,
                   hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "")
                  for p in root.rglob("*"))


class TestShelf:
    def test_binding_and_drift_without_touching_the_shelf(self, lib, shelf):
        lib.place_file("LIB-TEMPLATES-FORM-CLOSEOUT", "Templates", "Closeout", "Templates/closeout.md", PERSON,
                       object_type="FORM_TEMPLATE")
        before = _listing(shelf)
        clean = lib.scan_shelf()
        assert clean.counts()["CHANGED"] == 0 and clean.catalogued == 1
        assert _listing(shelf) == before, "a scan wrote to the shelf"

        (shelf / "Templates" / "closeout.md").write_text("edited in Explorer", encoding="utf-8")
        drift = lib.scan_shelf()
        assert [f[1] for f in drift.of("CHANGED")] == ["Templates/closeout.md"]
        assert lib.catalog.notices(notice_type="CHANGED")[0]["status"] == "OPEN"

        (shelf / "Templates" / "closeout.md").unlink()
        gone = lib.scan_shelf()
        assert [f[1] for f in gone.of("MISSING")] == ["Templates/closeout.md"]

    def test_mapping_findings_and_dry_run(self, lib, shelf):
        dry = lib.scan_shelf(record=False)
        assert dry.scan_id is None
        assert lib.catalog.counts()["catalog_scan"] == 0
        assert [f[1] for f in dry.of("UNMAPPED_FOLDER")] == ["Fuel"]
        assert [f[1] for f in dry.of("PLACEMENT_CONFLICT")] == ["Company Library/Agent Worker Constitutions/README.md"]
        recorded = lib.scan_shelf()
        summary = lib.catalog.scan_summary(recorded.scan_id)
        assert (summary["unmapped_folders"], summary["placement_conflicts"], summary["uncatalogued"]) == (1, 1, 2)

    def test_a_file_is_never_adopted_by_a_scan(self, lib, shelf):
        lib.scan_shelf()
        assert lib.list_current() == []

    @pytest.mark.skipif(not REAL_MEMORY.is_dir(), reason="D:\\Memory is not on this machine")
    def test_real_memory_dry_run_changes_nothing(self, tmp_path):
        before = _listing(REAL_MEMORY)
        service = open_library(tmp_path / "catalog.db", memory_root=REAL_MEMORY)
        report = service.scan_shelf(record=False)
        service.close()
        assert report.counts()["UNMAPPED_FOLDER"] == 6
        assert report.counts()["PLACEMENT_CONFLICT"] == 16
        assert _listing(REAL_MEMORY) == before
