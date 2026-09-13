"""Every schema case verified for LIBRARY_IMPLEMENTATION_PLAN_v2 section 7.2 (run 2).

Generated from the verifier that produced the plan's evidence, pointed at catalog/schema.sql
instead of the plan text. Importing this module runs the cases and fills RESULTS; the tests in
test_catalog_schema.py assert on them. Every refusal must be raised by SQLite itself.
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "src" / "dispatch_library" / "catalog" / "schema.sql"
RECIPES = Path(r"D:\Library\publisher_recipes.json")
if not RECIPES.is_file():  # off Mike's machine: the 2026-09-13 shape, from test_recipes.SAMPLE
    import tempfile
    from test_recipes import SAMPLE

    RECIPES = Path(tempfile.mkdtemp()) / "publisher_recipes.json"
    RECIPES.write_text(json.dumps(SAMPLE), encoding="utf-8")
T = "2026-09-13T20:00:00+00:00"
SHA_A = "a" * 64
SHA_B = "b" * 64

SCHEMA = SCHEMA_PATH.read_text(encoding="utf-8")
results = []
RESULTS = results


def fresh():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(SCHEMA)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("INSERT INTO schema_version VALUES (2, ?, 'corrected schema v2')", (T,))
    return db


def run(db, statements):
    db.execute("BEGIN")
    try:
        for sql, params in statements:
            db.execute(sql, params)
        db.execute("COMMIT")
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise


def refuse(name, db, statements):
    try:
        run(db, statements)
    except sqlite3.DatabaseError as exc:
        results.append(("REFUSED", name, str(exc).split("\n")[0][:110]))
        return
    results.append(("FAILED-ACCEPTED", name, "database accepted what it must refuse"))


def accept(name, db, statements, check=None):
    try:
        run(db, statements)
        if check is not None:
            check(db)
    except Exception as exc:  # noqa: BLE001
        results.append(("FAILED-REFUSED", name, f"{type(exc).__name__}: {exc}"))
        return
    results.append(("ACCEPTED", name, ""))


def obj(oid="libobj_1", code="LIB-TEMPLATES-FORM-BROKERCLOSEOUT", otype="FORM_TEMPLATE", coll="Templates"):
    return ("INSERT INTO library_object (library_object_id, object_code, object_type, collection_id, "
            "title, slug, canonical_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (oid, code, otype, coll, "Broker closeout", oid, "Broker closeout", T, T))


def approval(aid, oid, vid, approver="Mike Zachary", status="APPROVED", basis="HUMAN_PLACED",
             candidate=None, channel=None, ref=None):
    return ("INSERT INTO approval_record (approval_record_id, library_object_id, version_id, candidate_id, "
            "approver, approval_status, approval_basis, capture_channel, capture_ref, approved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, oid, vid, candidate, approver, status, basis, channel, ref, T))


def version(vid, oid, aid, major=1, minor=0, supersedes=None, path="Templates/closeout.md",
            sha=SHA_A, size=10, state="CURRENT"):
    bound = path is not None
    return ("INSERT INTO library_version (version_id, library_object_id, version_major, version_minor, "
            "lifecycle_state, title, content_uri, relative_path, content_sha256, size_bytes, "
            "observed_at, supersedes_version_id, approval_record_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, oid, major, minor, state, "Broker closeout", path or "inline:", path,
             sha if bound else None, size if bound else None, T if bound else None, supersedes, aid, T))


def place(oid="libobj_1", vid="libver_1", aid="apr_1", approver="Mike Zachary", channel=None, **kw):
    ok = {k: v for k, v in kw.items() if k in ("code", "otype", "coll")}
    vk = {k: v for k, v in kw.items() if k in ("path", "sha", "size")}
    return [obj(oid, **ok), approval(aid, oid, vid, approver=approver, channel=channel), version(vid, oid, aid, **vk)]


def flip(vid, state="SUPERSEDED"):
    return ("UPDATE library_version SET lifecycle_state = ? WHERE version_id = ?", (state, vid))


def supersede(db, old, new, aid, major, minor, oid="libobj_1"):
    run(db, [flip(old), approval(aid, oid, new), version(new, oid, aid, major, minor, supersedes=old)])


def candidate(cid="cand_1", role="DISPATCH", name=None, mission="MR-LOAD-1", workflow=None, status="SUBMITTED"):
    return ("INSERT INTO library_candidate (candidate_id, submitted_by_role, submitted_by_name, "
            "mission_record_id, workflow_event_id, source_type, proposed_collection_id, "
            "proposed_object_code, proposed_title, proposed_body_or_reference, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, role, name, mission, workflow, "load_closeout", "Location_Intelligence",
             "LIB-LOCATION_INTELLIGENCE-FACILITY-DOCK7", "Dock 7 gate notes", "Gate code at north entry", status, T))


def queued(cid="cand_1"):
    return ("UPDATE library_candidate SET status='PENDING_REVIEW' WHERE candidate_id=?", (cid,))


def classified(cid="cand_1", otype="VALIDATED_INTELLIGENCE_SUMMARY"):
    return ("UPDATE library_candidate SET recommended_object_type=? WHERE candidate_id=?", (otype, cid))


def confirmed(cid="cand_1", by="Dispatch", otype="VALIDATED_INTELLIGENCE_SUMMARY"):
    return ("UPDATE library_candidate SET proposed_object_type=?, object_type_confirmed_by=?, "
            "object_type_confirmed_at=? WHERE candidate_id=?", (otype, by, T, cid))


def validated(cid="cand_1"):
    return ("UPDATE library_candidate SET status='VALIDATED', validation_result='PASSED', validated_at=? "
            "WHERE candidate_id=?", (T, cid))


def ready(cid="cand_1", **kw):
    return [candidate(cid, **kw), queued(cid), classified(cid), confirmed(cid, by=kw.get("role", "DISPATCH").title()), validated(cid)]


CAND_OBJ = lambda otype="VALIDATED_INTELLIGENCE_SUMMARY", coll="Location_Intelligence": obj(
    "libobj_c", "LIB-LOCATION_INTELLIGENCE-FACILITY-DOCK7", otype, coll)

NOTICE = ("INSERT INTO library_notice (notice_id, notice_type, relative_path, candidate_id, missing_field, "
          "recommended_object_type, recommended_action, raised_at) VALUES (?,?,?,?,?,?,?,?)")

# ── refusals carried from run 1, adjusted to the rulings ───────────────────
refuse("R01 a sixteenth collection", fresh(), [("INSERT INTO library_collection (collection_id, name) VALUES ('Fuel','Fuel')", ())])
refuse("R02 object in a collection outside the fifteen", fresh(), [obj(coll="Archive")])
refuse("R03 object_code carrying its version suffix", fresh(), [obj(code="LIB-TEMPLATES-FORM-X-v1.0")])
refuse("R04 object type outside COM section 4", fresh(), [obj(otype="MEMO")])
refuse("R04b object with no object type (ruling 3)", fresh(), [obj(otype=None)])

db = fresh(); run(db, place())
refuse("R05 changing an object's collection", db, [("UPDATE library_object SET collection_id='Reference' WHERE library_object_id='libobj_1'", ())])
refuse("R05b changing an object's type", db, [("UPDATE library_object SET object_type='PACKET' WHERE library_object_id='libobj_1'", ())])
refuse("R06 deleting an object", db, [("DELETE FROM library_object WHERE library_object_id='libobj_1'", ())])
refuse("R07 version with no approval record", fresh(), [obj(), version("libver_1", "libobj_1", "apr_missing")])
refuse("R08 version whose approval names a different version", fresh(),
       [obj(), approval("apr_1", "libobj_1", "libver_other"), version("libver_1", "libobj_1", "apr_1")])

for who in (" publisher ", "Dispatch", "LIBRARY", "system", "AUTOMATION", "Intelligence",
            "Joe", " JOE ", "comi", "COMI", "Email Helper", "email-helper", "EMAIL_HELPER"):
    refuse(f"R09 approver {who!r} (ruling 6)", fresh(), place(approver=who))

db = fresh(); run(db, place())
refuse("R10 later version while v1 is still current", db,
       [approval("apr_2", "libobj_1", "libver_2"), version("libver_2", "libobj_1", "apr_2", 1, 1, path=None)])
db = fresh(); run(db, place()); db.execute("DROP TRIGGER library_version_supersedes_correctly")
refuse("R11 second current version with supersession trigger dropped: index holds", db,
       [approval("apr_2", "libobj_1", "libver_2"), version("libver_2", "libobj_1", "apr_2", 1, 1, path=None)])
db = fresh(); run(db, place())
refuse("R12 new version not later (1.0 again)", db,
       [flip("libver_1"), approval("apr_2", "libobj_1", "libver_2"), version("libver_2", "libobj_1", "apr_2", 1, 0, supersedes="libver_1", path=None)])
refuse("R13 first version superseding something", fresh(),
       [obj(), approval("apr_1", "libobj_1", "libver_1"), version("libver_1", "libobj_1", "apr_1", supersedes="libver_x")])
refuse("R14 version entering as SUPERSEDED", fresh(),
       [obj(), approval("apr_1", "libobj_1", "libver_1"), version("libver_1", "libobj_1", "apr_1", state="SUPERSEDED")])
refuse("R14b version entering under the retired name APPROVED_CURRENT", fresh(),
       [obj(), approval("apr_1", "libobj_1", "libver_1"), version("libver_1", "libobj_1", "apr_1", state="APPROVED_CURRENT")])

db = fresh(); run(db, place())
refuse("R15 editing approved content (sha256)", db, [("UPDATE library_version SET content_sha256=? WHERE version_id='libver_1'", (SHA_B,))])
refuse("R16 editing approved title", db, [("UPDATE library_version SET title='Renamed' WHERE version_id='libver_1'", ())])
refuse("R17 deleting a version", db, [("DELETE FROM library_version WHERE version_id='libver_1'", ())])
db = fresh(); run(db, place()); supersede(db, "libver_1", "libver_2", "apr_2", 1, 1)
refuse("R18 SUPERSEDED back to CURRENT", db, [flip("libver_1", "CURRENT")])
refuse("R19 ARCHIVED_VERSION_RECORD without an Archive link", db, [flip("libver_1", "ARCHIVED_VERSION_RECORD")])
db = fresh(); run(db, place())
refuse("R20 second object claiming the same file, different case", db,
       place("libobj_2", "libver_9", "apr_9", code="LIB-TEMPLATES-FORM-OTHER", path="templates/CLOSEOUT.md"))
refuse("R21 malformed SHA-256", fresh(), place(sha="XYZ"))
refuse("R22 uppercase SHA-256", fresh(), place(sha="A" * 64))
refuse("R23 absolute Windows path", fresh(), place(path="D:/Memory/Templates/x.md"))
refuse("R24 path escaping the shelf", fresh(), place(path="Templates/../../x.md"))
refuse("R25 backslash path", fresh(), place(path="Templates\\x.md"))
refuse("R26 half a shelf binding", fresh(), place(size=None))
refuse("R27 approval naming a version that never arrives (deferred FK)", fresh(), [obj(), approval("apr_1", "libobj_1", "libver_never")])

refuse("R28 Dispatch candidate with no Mission Record or workflow event", fresh(), [candidate(mission=None)])
refuse("R29 human candidate with no name", fresh(), [candidate(role="HUMAN", mission=None)])
for nm in ("Publisher", "Joe", "email helper"):
    refuse(f"R30 human candidate named {nm!r}", fresh(), [candidate(role="HUMAN", name=nm, mission=None)])
refuse("R31 Manager as a candidate source", fresh(), [candidate(role="MANAGER")])
refuse("R32 Library nominating to itself (ruling 5)", fresh(), [candidate(role="LIBRARY")])
refuse("R32b Joe as a candidate source", fresh(), [candidate(role="JOE")])
refuse("R33 candidate entering as PENDING_REVIEW, skipping SUBMITTED", fresh(), [candidate(status="PENDING_REVIEW")])
refuse("R33b candidate entering as APPROVED", fresh(), [candidate(status="APPROVED")])

db = fresh(); run(db, [candidate(), queued()])
refuse("R34 approving a candidate never validated", db,
       [CAND_OBJ(), approval("apr_c", "libobj_c", "libver_c", basis="CANDIDATE_REVIEW", candidate="cand_1")])
refuse("R35 PENDING_REVIEW to APPROVED with no approval record", db,
       [("UPDATE library_candidate SET status='APPROVED', reviewed_by='Mike Zachary', reviewed_at=? WHERE candidate_id='cand_1'", (T,))])
refuse("R36 validating without a confirmed object type (ruling 3)", db,
       [classified(), validated()])
refuse("R36b validating with only Library's recommendation", db,
       [classified(), ("UPDATE library_candidate SET proposed_object_type='VALIDATED_INTELLIGENCE_SUMMARY' WHERE candidate_id='cand_1'", ()), validated()])

db = fresh(); run(db, [candidate(), confirmed()])
refuse("R35b SUBMITTED to VALIDATED, skipping PENDING_REVIEW (transition trigger)", db, [validated()])

db = fresh(); run(db, ready())
refuse("R37 candidate approved with no approval record", db,
       [("UPDATE library_candidate SET status='APPROVED', reviewed_by='Mike Zachary', reviewed_at=? WHERE candidate_id='cand_1'", (T,))])
refuse("R38 candidate decision recorded by a different reviewer", db,
       [("INSERT INTO approval_record (approval_record_id, candidate_id, approver, approval_status, approval_basis, approved_at) "
         "VALUES ('apr_r','cand_1','Mike Zachary','REJECTED','CANDIDATE_REVIEW',?)", (T,)),
        ("UPDATE library_candidate SET status='REJECTED', reviewed_by='Someone Else', reviewed_at=? WHERE candidate_id='cand_1'", (T,))])

db = fresh(); run(db, place())
refuse("R39 editing an approval record", db, [("UPDATE approval_record SET approver='Someone Else' WHERE approval_record_id='apr_1'", ())])
refuse("R40 deleting an approval record", db, [("DELETE FROM approval_record WHERE approval_record_id='apr_1'", ())])
refuse("R41 Manager as a consumer role", db, [("INSERT INTO library_object_consumer VALUES ('libobj_1','Manager')", ())])
refuse("R42 Manager as owner role", db, [("UPDATE library_object SET owner_role='MANAGER' WHERE library_object_id='libobj_1'", ())])

db = fresh(); run(db, place()); supersede(db, "libver_1", "libver_2", "apr_2", 1, 1)
refuse("R43 current-only retrieval returning a superseded version", db,
       [("INSERT INTO retrieval_event (consumer_role, requested_object_code, library_object_id, version_id, outcome, retrieved_at) "
         "VALUES ('Publisher','X','libobj_1','libver_1','RETURNED',?)", (T,))])
run(db, [flip("libver_2", "REVIEW_DUE")])
refuse("R44 current-only retrieval returning a REVIEW_DUE version", db,
       [("INSERT INTO retrieval_event (consumer_role, requested_object_code, library_object_id, version_id, outcome, retrieved_at) "
         "VALUES ('Publisher','X','libobj_1','libver_2','RETURNED',?)", (T,))])
run(db, [("INSERT INTO retrieval_event (consumer_role, requested_object_code, outcome, retrieved_at) VALUES ('Publisher','X','MISSING',?)", (T,))])
refuse("R45 editing a retrieval event", db, [("UPDATE retrieval_event SET outcome='RETURNED'", ())])
refuse("R46 deleting a retrieval event", db, [("DELETE FROM retrieval_event", ())])
refuse("R47 queuing a current version for archive review", db,
       [("INSERT INTO archive_review_queue (version_id, queued_at) VALUES ('libver_2', ?)", (T,))])
refuse("R48 RETENTION_REVIEW without the queue", db,
       [("INSERT INTO archive_link (archive_link_id, library_object_id, version_id, archive_record_id, relationship_type, created_at) "
         "VALUES ('al_1','libobj_1','libver_1','ARC-1','SUPERSEDED_VERSION',?)", (T,)),
        flip("libver_1", "ARCHIVED_VERSION_RECORD"), flip("libver_1", "RETENTION_REVIEW")])

db = fresh(); run(db, place()); supersede(db, "libver_1", "libver_2", "apr_2", 1, 1)
run(db, [("INSERT INTO archive_link (archive_link_id, library_object_id, version_id, archive_record_id, relationship_type, created_at) "
          "VALUES ('al_1','libobj_1','libver_1','ARC-1','SUPERSEDED_VERSION',?)", (T,)),
         flip("libver_1", "ARCHIVED_VERSION_RECORD"),
         ("INSERT INTO archive_review_queue (version_id, queued_at) VALUES ('libver_1', ?)", (T,))])
refuse("R49 archive disposition with no decider", db, [("UPDATE archive_review_queue SET disposition='DELETE' WHERE version_id='libver_1'", ())])
refuse("R50 archive disposition decided by Joe", db,
       [("UPDATE archive_review_queue SET disposition='DELETE', decided_by='joe', decided_at=? WHERE version_id='libver_1'", (T,))])

recipe_cols = ("INSERT INTO publisher_recipe (recipe_id, recipe_code, recipe_type, version, status, is_placeholder, "
               "recipe_name, source_key, human_review_required, source_path, source_sha256, loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")
db = fresh(); run(db, [(recipe_cols, ("rec_pod", "RECIPE-POD_PACKAGE-v1", "POD_PACKAGE", 1, "CURRENT", 1, None, None, None, None, None, T))])
refuse("R51 placeholder recipe given a requirement", db, [("INSERT INTO recipe_requirement VALUES ('rec_pod','COMPANY_ITEM','w9',0)", ())])
refuse("R52 placeholder recipe carrying source fields", fresh(),
       [(recipe_cols, ("rec_x", "RECIPE-X", "POD_PACKAGE", 1, "CURRENT", 1, "Name", "pod", 1, "p", SHA_A, T))])
refuse("R53 second current recipe of one type", db,
       [(recipe_cols, ("rec_pod2", "RECIPE-POD_PACKAGE-v2", "POD_PACKAGE", 2, "CURRENT", 1, None, None, None, None, None, T))])

db = fresh(); run(db, [("INSERT INTO catalog_scan (started_at, finished_at, memory_root) VALUES (?,?,?)", (T, T, "D:/Memory"))])
refuse("R54 finding added to a finished scan", db, [("INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (1,'Fuel','UNMAPPED_FOLDER')", ())])
refuse("R55 editing a finished scan", db, [("UPDATE catalog_scan SET files_seen=99", ())])
run(db, [("INSERT INTO catalog_scan (started_at, memory_root) VALUES (?,?)", (T, "D:/Memory"))])
refuse("R56 CHANGED finding naming no version", db, [("INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (2,'Templates/a.md','CHANGED')", ())])

db = fresh(); run(db, place())
refuse("R57 object related to itself", db, [("INSERT INTO object_relationship VALUES ('rel_1','libobj_1','libobj_1','DEPENDS_ON',1,?)", (T,))])
run(db, place("libobj_2", "libver_2", "apr_2", code="LIB-COMPANY-W9-X", otype="COMPANY_CREDENTIAL", coll="Company", path="Company/w9.pdf"))
refuse("R58 metadata version from another object", db,
       [("INSERT INTO library_metadata VALUES ('md_1','libobj_1','libver_2','expiration_date','2027-01-01','DATE')", ())])
refuse("R59 editing a version's source reference", db,
       [("INSERT INTO source_ref VALUES ('sr_1','libver_1',NULL,'SHELF_FILE','Templates/closeout.md','')", ()),
        ("UPDATE source_ref SET reference='elsewhere' WHERE source_ref_id='sr_1'", ())])

# ── refusals new in run 2 ──────────────────────────────────────────────────
db = fresh(); run(db, [candidate(), queued(), classified()])
refuse("R60 Library confirming the object type (ruling 5)", db, [confirmed(by="Library")])
refuse("R61 Joe confirming the object type", db, [confirmed(by="JOE")])
refuse("R62 a different system confirming (Dispatch candidate, Publisher confirms)", db, [confirmed(by="Publisher")])
refuse("R62b 'Human' as a confirmer name", db, [confirmed(by="Human")])
refuse("R63 confirmation time without a confirmer", db,
       [("UPDATE library_candidate SET proposed_object_type='PACKET', object_type_confirmed_at=? WHERE candidate_id='cand_1'", (T,))])
db = fresh(); run(db, [candidate(), queued(), confirmed()])
refuse("R64 changing a confirmed object type without reconfirming", db,
       [("UPDATE library_candidate SET proposed_object_type='PACKET' WHERE candidate_id='cand_1'", ())])
db = fresh(); run(db, ready())
refuse("R65 approving into an object of a different type than confirmed", db,
       [CAND_OBJ(otype="PACKET"), approval("apr_c", "libobj_c", "libver_c", basis="CANDIDATE_REVIEW", candidate="cand_1")])
refuse("R66 approving into an object in a different collection than proposed", db,
       [CAND_OBJ(coll="Reference"), approval("apr_c", "libobj_c", "libver_c", basis="CANDIDATE_REVIEW", candidate="cand_1")])
refuse("R67 capture reference with no capture channel", fresh(),
       [obj(), ("INSERT INTO approval_record (approval_record_id, library_object_id, version_id, approver, approval_status, "
                "approval_basis, capture_ref, approved_at) VALUES ('apr_1','libobj_1','libver_1','Mike Zachary','APPROVED','HUMAN_PLACED','joe-msg-1',?)", (T,)),
        version("libver_1", "libobj_1", "apr_1")])
refuse("R68 MISSING_FIELD notice that names no field", fresh(),
       [(NOTICE, ("n_1", "MISSING_FIELD", "Company Library/x.docx", None, None, None, "", T))])
refuse("R69 notice about nothing", fresh(), [(NOTICE, ("n_1", "CONFLICT", None, None, None, None, "", T))])
refuse("R70 notice recommending a type outside COM section 4", fresh(),
       [(NOTICE, ("n_1", "MISSING_FIELD", "Company Library/x.docx", None, "object_type", "MEMO", "", T))])
db = fresh(); run(db, [(NOTICE, ("n_1", "MISSING_FIELD", "Company Library/x.docx", None, "object_type", "CONSTITUTION_PACKAGE", "confirm type", T))])
for who in ("LIBRARY", "Joe", "automation", "Email Helper"):
    refuse(f"R71 notice resolved by {who!r}", db,
           [("UPDATE library_notice SET status='RESOLVED', resolved_by=?, resolved_at=?, resolution='done' WHERE notice_id='n_1'", (who, T))])
refuse("R72 notice resolved with no resolution text", db,
       [("UPDATE library_notice SET status='RESOLVED', resolved_by='Mike Zachary', resolved_at=? WHERE notice_id='n_1'", (T,))])
run(db, [("UPDATE library_notice SET status='RESOLVED', resolved_by='Mike Zachary', resolved_at=?, resolution='confirmed CONSTITUTION_PACKAGE' WHERE notice_id='n_1'", (T,))])
refuse("R73 editing a resolved notice", db, [("UPDATE library_notice SET resolution='changed my mind' WHERE notice_id='n_1'", ())])
refuse("R74 deleting a notice", db, [("DELETE FROM library_notice WHERE notice_id='n_1'", ())])

# ── acceptances ────────────────────────────────────────────────────────────
def one_current(db, oid="libobj_1"):
    n = db.execute("SELECT count(*) FROM library_version WHERE library_object_id=? AND is_current=1", (oid,)).fetchone()[0]
    assert n == 1, f"expected exactly one current version, found {n}"


def check_placed(db):
    row = db.execute("SELECT versioned_code, approver, approval_basis, lifecycle_state, capture_channel FROM library_current").fetchone()
    assert row == ("LIB-TEMPLATES-FORM-BROKERCLOSEOUT-v1.0", "Mike Zachary", "HUMAN_PLACED", "CURRENT", None), row
    one_current(db)


accept("A01 human places a document directly: no second gate", fresh(), place(), check_placed)


def check_joe(db):
    row = db.execute("SELECT approver, capture_channel FROM library_current").fetchone()
    assert row == ("Mike Zachary", "JOE"), row


accept("A02 Mike approves through Joe: Mike is approver, Joe the capture channel (ruling 6)", fresh(),
       [obj(), approval("apr_1", "libobj_1", "libver_1", channel="JOE", ref="joe-capture-2026-09-13-1"),
        version("libver_1", "libobj_1", "apr_1")], check_joe)
accept("A03 a human named Joe Smith is not refused (normalisation does not over-match)", fresh(), place(approver="Joe Smith"))

db = fresh(); run(db, place())


def check_lineage(db):
    one_current(db)
    rows = db.execute("SELECT version_major, version_minor, lifecycle_state, superseded_by_version_id "
                      "FROM library_version_lineage ORDER BY version_major, version_minor").fetchall()
    assert rows == [(1, 0, "SUPERSEDED", "libver_2"), (1, 1, "SUPERSEDED", "libver_3"), (2, 0, "CURRENT", None)], rows


accept("A04 transactional supersession 1.0 -> 1.1 -> 2.0", db,
       [flip("libver_1"), approval("apr_2", "libobj_1", "libver_2"),
        version("libver_2", "libobj_1", "apr_2", 1, 1, supersedes="libver_1", sha=SHA_B),
        flip("libver_2"), approval("apr_3", "libobj_1", "libver_3"),
        version("libver_3", "libobj_1", "apr_3", 2, 0, supersedes="libver_2")], check_lineage)

db = fresh(); run(db, place())
try:
    db.execute("BEGIN"); db.execute(*flip("libver_1")); raise RuntimeError("simulated crash")
except RuntimeError:
    db.execute("ROLLBACK")
accept("A05 crash between flip and insert rolls back to exactly one current", db, [], one_current)


def check_candidate(db):
    assert db.execute("SELECT status, reviewed_by FROM library_candidate").fetchone() == ("APPROVED", "Mike Zachary")
    assert db.execute("SELECT approval_basis, lifecycle_state FROM library_current WHERE library_object_id='libobj_c'").fetchone() == ("CANDIDATE_REVIEW", "CURRENT")


accept("A06 Dispatch + Mission Record: SUBMITTED -> PENDING_REVIEW -> classified -> type confirmed by Dispatch -> VALIDATED -> APPROVED -> CURRENT",
       fresh(),
       ready() + [CAND_OBJ(), approval("apr_c", "libobj_c", "libver_c", basis="CANDIDATE_REVIEW", candidate="cand_1"),
                  version("libver_c", "libobj_c", "apr_c", path=None),
                  ("INSERT INTO source_ref VALUES ('sr_c',NULL,'cand_1','MISSION_RECORD','MR-LOAD-1','')", ()),
                  ("UPDATE library_candidate SET status='APPROVED', reviewed_by='Mike Zachary', reviewed_at=? WHERE candidate_id='cand_1'", (T,))],
       check_candidate)

accept("A07 Intelligence candidate, type confirmed by Intelligence as the submitting source", fresh(), ready(role="INTELLIGENCE", mission=None))
accept("A08 Publisher candidate, type confirmed by Mike rather than the source", fresh(),
       [candidate(role="PUBLISHER", mission=None), queued(), classified(), confirmed(by="Mike Zachary"), validated()])
accept("A09 human candidate by Mike: type confirmed by Mike, validated", fresh(),
       [candidate(role="HUMAN", name="Mike Zachary", mission=None), queued(), confirmed(by="Mike Zachary"), validated()])
accept("A10 Dispatch candidate tied to a workflow event instead of a Mission Record", fresh(), [candidate(mission=None, workflow="WF-POD-UPLOAD-7")])
accept("A11 confirmed type changed with a fresh confirmation", fresh(),
       [candidate(), queued(), confirmed(),
        ("UPDATE library_candidate SET proposed_object_type='PACKET', object_type_confirmed_at='2026-09-13T21:00:00+00:00' WHERE candidate_id='cand_1'", ())])

db = fresh(); run(db, [candidate(), queued()])
accept("A12 candidate deferred by Mike, then back to PENDING_REVIEW", db,
       [("INSERT INTO approval_record (approval_record_id, candidate_id, approver, approval_status, approval_basis, approved_at) "
         "VALUES ('apr_d','cand_1','Mike Zachary','DEFERRED','CANDIDATE_REVIEW',?)", (T,)),
        ("UPDATE library_candidate SET status='DEFERRED', reviewed_by='Mike Zachary', reviewed_at=? WHERE candidate_id='cand_1'", (T,)),
        ("UPDATE library_candidate SET status='PENDING_REVIEW', reviewed_by=NULL, reviewed_at=NULL WHERE candidate_id='cand_1'", ())])


def check_missing_type(db):
    assert db.execute("SELECT count(*) FROM library_object").fetchone()[0] == 0
    assert db.execute("SELECT status, resolved_by FROM library_notice WHERE notice_id='n_1'").fetchone() == ("RESOLVED", "Mike Zachary")
    assert db.execute("SELECT object_type FROM library_current").fetchone() is None


db = fresh()
accept("A13 object type missing: no object, MISSING_FIELD notice with a recommendation, asset stays uncatalogued, Mike resolves", db,
       [("INSERT INTO catalog_scan (started_at, memory_root, files_seen) VALUES (?,?,1)", (T, "D:/Memory")),
        ("INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (1,'Company Library/Agent Worker Constitutions/05_LIBRARY_WORKER_CONSTITUTION.md','UNCATALOGUED')", ()),
        ("INSERT INTO library_notice (notice_id, notice_type, relative_path, scan_id, missing_field, recommended_object_type, "
         "recommended_action, raised_at) VALUES ('n_1','MISSING_FIELD','Company Library/Agent Worker Constitutions/05_LIBRARY_WORKER_CONSTITUTION.md',1,"
         "'object_type','ROLE_DOCTRINE','confirm object type before acceptance',?)", (T,)),
        ("UPDATE library_notice SET status='RESOLVED', resolved_by='Mike Zachary', resolved_at=?, resolution='confirmed ROLE_DOCTRINE' WHERE notice_id='n_1'", (T,))],
       check_missing_type)
accept("A14 BLOCKED_WORK and CONFLICT notices raised by Library; a conflict resolved by Publisher as an authorised source", fresh(),
       [candidate(), (NOTICE, ("n_b", "BLOCKED_WORK", None, "cand_1", None, None, "Publisher packet waits on this candidate", T)),
        (NOTICE, ("n_c", "CONFLICT", "Company/w9.pdf", None, None, None, "two W-9 copies on the shelf", T)),
        ("UPDATE library_notice SET status='RESOLVED', resolved_by='Publisher', resolved_at=?, resolution='newer copy nominated' WHERE notice_id='n_c'", (T,))])

db = fresh(); run(db, place()); supersede(db, "libver_1", "libver_2", "apr_2", 1, 1)
accept("A15 superseded -> Archive link -> archived record -> queue -> RETENTION_REVIEW -> KEEP by Mike", db,
       [("INSERT INTO archive_link (archive_link_id, library_object_id, version_id, archive_record_id, relationship_type, created_at) "
         "VALUES ('al_1','libobj_1','libver_1','ARC-2026-0913-1','SUPERSEDED_VERSION',?)", (T,)),
        flip("libver_1", "ARCHIVED_VERSION_RECORD"),
        ("INSERT INTO archive_review_queue (version_id, queued_at) VALUES ('libver_1', ?)", (T,)),
        flip("libver_1", "RETENTION_REVIEW"),
        ("UPDATE archive_review_queue SET disposition='KEEP', decided_by='Mike Zachary', decided_at=? WHERE version_id='libver_1'", (T,))])

db = fresh(); run(db, place())
accept("A16 CURRENT -> ACTIVE_USE -> REVIEW_DUE -> ACTIVE_USE, with a conflict notice linked", db,
       [flip("libver_1", "ACTIVE_USE"), flip("libver_1", "REVIEW_DUE"),
        (NOTICE, ("n_x", "EXPIRED", None, None, None, None, "renew before external use", T)) if False else
        ("INSERT INTO library_notice (notice_id, notice_type, version_id, recommended_action, raised_at) VALUES ('n_x','EXPIRED','libver_1','renew before external use',?)", (T,)),
        ("UPDATE library_version SET conflict_notice_id='n_x' WHERE version_id='libver_1'", ()),
        flip("libver_1", "ACTIVE_USE")], one_current)

raw = RECIPES.read_bytes(); recipes = json.loads(raw); stmts = []
for key, rtype in (("broker_onboarding", "BROKER_ONBOARDING_PACKET"), ("government_proposal", "GOVERNMENT_PROPOSAL_PACKET")):
    r = recipes[key]; rid = f"rec_{key}"
    stmts.append((recipe_cols, (rid, f"RECIPE-{rtype}-v1", rtype, 1, "CURRENT", 0, r["recipe_name"], key,
                                int(r["human_review_required"]), str(RECIPES), hashlib.sha256(raw).hexdigest(), T)))
    for kind, field in (("COMPANY_ITEM", "required_company_items"), ("PUBLISHER_ITEM", "required_publisher_items"),
                        ("HUMAN_ITEM", "required_human_items"), ("OUTPUT", "required_outputs")):
        for pos, value in enumerate(r[field]):
            stmts.append(("INSERT INTO recipe_requirement VALUES (?,?,?,?)", (rid, kind, value, pos)))
for p in ("VISIBILITY_STATUS_PACKET", "POD_PACKAGE", "REVIEW_PACKAGE"):
    stmts.append((recipe_cols, (f"rec_{p}", f"RECIPE-{p}-v1", p, 1, "CURRENT", 1, None, None, None, None, None, T)))


def check_recipes(db):
    for key in ("broker_onboarding", "government_proposal"):
        for kind, field in (("COMPANY_ITEM", "required_company_items"), ("PUBLISHER_ITEM", "required_publisher_items"),
                            ("HUMAN_ITEM", "required_human_items"), ("OUTPUT", "required_outputs")):
            got = [v for (v,) in db.execute("SELECT value FROM recipe_requirement WHERE recipe_id=? AND kind=? ORDER BY position", (f"rec_{key}", kind))]
            assert got == recipes[key][field], (key, kind, got)
    assert db.execute("SELECT count(*) FROM publisher_recipe WHERE is_placeholder=1").fetchone()[0] == 3


accept("A17 the real publisher_recipes.json stored losslessly; three placeholders carry nothing", fresh(), stmts, check_recipes)

db = fresh(); run(db, place())
accept("A18 scan: UNMAPPED_FOLDER, PLACEMENT_CONFLICT, UNCATALOGUED, CHANGED; summary derived", db,
       [("INSERT INTO catalog_scan (started_at, memory_root, files_seen, folders_seen) VALUES (?,?,16,18)", (T, "D:/Memory"))]
       + [("INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (1,?,'UNMAPPED_FOLDER')", (f,))
          for f in ("Operational Intelligence", "Receipts", "Fuel", "Drivers", "Evidence", "Documents")]
       + [("INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (1,'Company Library/Freight Visibility for Regional Carriers 2.docx','PLACEMENT_CONFLICT')", ()),
          ("INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (1,'Company Library/new.docx','UNCATALOGUED')", ()),
          ("INSERT INTO catalog_finding (scan_id, relative_path, finding, version_id, observed_sha256) VALUES (1,'Templates/closeout.md','CHANGED','libver_1',?)", (SHA_B,)),
          ("UPDATE catalog_scan SET finished_at=? WHERE scan_id=1", (T,))],
       lambda d: [None for r in [d.execute("SELECT files_seen, folders_seen, unmapped_folders, placement_conflicts, uncatalogued, changed, missing FROM catalog_scan_summary").fetchone()] if r == (16, 18, 6, 1, 1, 1, 0)] or (_ for _ in ()).throw(AssertionError("summary")))

db = fresh(); run(db, place())
accept("A19 retrieval events RETURNED, MISSING, ARCHIVE_REFERENCE_ONLY", db,
       [("INSERT INTO retrieval_event (consumer_role, requested_object_code, library_object_id, version_id, outcome, retrieved_at) VALUES ('Publisher','X','libobj_1','libver_1','RETURNED',?)", (T,)),
        ("INSERT INTO retrieval_event (consumer_role, requested_object_code, outcome, retrieved_at) VALUES ('Publisher','w9','MISSING',?)", (T,)),
        ("INSERT INTO retrieval_event (consumer_role, requested_object_code, library_object_id, current_only, outcome, retrieved_at) VALUES ('Archive','X','libobj_1',0,'ARCHIVE_REFERENCE_ONLY',?)", (T,))])

db = fresh(); run(db, place())
run(db, place("libobj_2", "libver_2", "apr_2", code="LIB-COMPANY-W9-LEVEL1TRANSPORT", otype="COMPANY_CREDENTIAL", coll="Company", path="Company/w9.pdf"))
accept("A20 metadata, source refs, tags, consumers, relationships, drift update", db,
       [("INSERT INTO library_metadata VALUES ('md_1','libobj_2','libver_2','expiration_date','2027-01-01','DATE')", ()),
        ("INSERT INTO library_metadata VALUES ('md_2','libobj_2',NULL,'issuing_authority','IRS','TEXT')", ()),
        ("INSERT INTO source_ref VALUES ('sr_1','libver_2',NULL,'SHELF_FILE','Company/w9.pdf','')", ()),
        ("INSERT INTO library_object_tag VALUES ('libobj_2','credential',0)", ()),
        ("INSERT INTO library_object_consumer VALUES ('libobj_2','Publisher')", ()),
        ("INSERT INTO object_relationship VALUES ('rel_1','libobj_1','libobj_2','DEPENDS_ON',1,?)", (T,)),
        ("UPDATE library_version SET drift_check_result='FAILED', observed_at=? WHERE version_id='libver_2'", (T,))])
accept("A21 an Index manifest in the Index collection", fresh(),
       place("libobj_ix", "libver_ix", "apr_ix", code="LIB-INDEX-MANIFEST-MEMORYFOLDERMAP", otype="LIBRARY_INDEX_MANIFEST", coll="Index", path="Index/memory_folder_mapping.json"))
db = fresh(); run(db, [obj()])
accept("A22 an object with no version is reported", db, [],
       lambda d: None if d.execute("SELECT count(*) FROM library_object_without_version").fetchone()[0] == 1 else (_ for _ in ()).throw(AssertionError("orphan")))

