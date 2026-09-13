"""What the catalog refuses, and why each refusal is in the database.

Every rule checked here is already enforced in `models.py` or `ingestion.py`.
These tests exist because those rules protect the objects *this package*
constructs, and a database outlives the code that created it: a migration
script, a repair session, a future service, or a person with a SQLite browser
can all write to this file without going through a dataclass.

A rule that only lives in Python is a rule that holds until someone bypasses
Python.
"""
from __future__ import annotations

import sqlite3

import pytest

from dispatch_library.catalog import (
    CatalogVersionError,
    SCHEMA_VERSION,
    connect,
    current_version,
    migrate,
    open_catalog,
)

OBJECT_COLUMNS = (
    "object_code, version, collection, title, status, source, "
    "body_or_uri, accepted_by, accepted_at, relative_path"
)


def _object(connection, **overrides):
    row = dict(
        object_code="DOC-1",
        version=1,
        collection="Reference",
        title="A document",
        status="CURRENT",
        source="HUMAN_PLACED",
        body_or_uri="Reference/doc.md",
        accepted_by="Mike Zachary",
        accepted_at="2026-09-13T00:00:00+00:00",
        relative_path=None,
    )
    row.update(overrides)
    connection.execute(
        f"INSERT INTO library_object ({OBJECT_COLUMNS}) VALUES (:object_code, :version, "
        ":collection, :title, :status, :source, :body_or_uri, :accepted_by, :accepted_at, "
        ":relative_path)",
        row,
    )
    return row


CANDIDATE_COLUMNS = (
    "candidate_id, submitted_by, source_type, collection, proposed_object_code, "
    "proposed_title, proposed_body_or_reference, status, reviewed_by, created_at"
)


def _candidate(connection, **overrides):
    row = dict(
        candidate_id="cand-1",
        submitted_by="INTELLIGENCE",
        source_type="finding",
        collection="Reference",
        proposed_object_code="DOC-9",
        proposed_title="Proposed",
        proposed_body_or_reference="body",
        status="PENDING_REVIEW",
        reviewed_by=None,
        created_at="2026-09-13T00:00:00+00:00",
    )
    row.update(overrides)
    connection.execute(
        f"INSERT INTO library_candidate ({CANDIDATE_COLUMNS}) VALUES (:candidate_id, "
        ":submitted_by, :source_type, :collection, :proposed_object_code, :proposed_title, "
        ":proposed_body_or_reference, :status, :reviewed_by, :created_at)",
        row,
    )
    return row


@pytest.fixture()
def catalog():
    connection = open_catalog()
    yield connection
    connection.close()


class TestTheCatalogOpens:
    def test_a_new_catalog_is_at_the_current_schema_version(self, catalog):
        assert current_version(catalog) == SCHEMA_VERSION

    def test_every_table_the_schema_declares_is_present(self, catalog):
        present = {
            row["name"]
            for row in catalog.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "library_object", "library_object_tag", "library_candidate",
            "publisher_recipe", "recipe_requirement", "archive_review_queue",
            "catalog_scan", "catalog_finding", "schema_version",
        } <= present

    def test_foreign_keys_are_on_for_the_connection(self, catalog):
        """Per-connection in SQLite, not a property of the file. Setting it only
        in schema.sql would enforce it once, on the connection that created the
        database, and never again."""
        assert catalog.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_migrating_twice_changes_nothing(self, catalog):
        assert migrate(catalog) == SCHEMA_VERSION
        assert migrate(catalog) == SCHEMA_VERSION
        rows = catalog.execute("SELECT count(*) AS n FROM schema_version").fetchone()["n"]
        assert rows == 1

    def test_an_empty_database_reports_version_zero(self):
        connection = connect()
        assert current_version(connection) == 0
        connection.close()

    def test_a_catalog_from_a_newer_library_is_refused(self):
        """Opening it read-write would quietly drop columns the newer version
        writes. Refusing is the safe answer, and it names the two versions."""
        connection = open_catalog()
        connection.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION + 1, "2027-01-01T00:00:00+00:00"),
        )
        with pytest.raises(CatalogVersionError) as raised:
            migrate(connection)
        assert str(SCHEMA_VERSION + 1) in str(raised.value)
        connection.close()

    def test_a_catalog_on_disk_survives_being_closed(self, tmp_path):
        path = tmp_path / "nested" / "catalog.db"
        first = open_catalog(path)
        _object(first)
        first.commit()
        first.close()

        second = open_catalog(path)
        assert second.execute("SELECT count(*) AS n FROM library_object").fetchone()["n"] == 1
        assert current_version(second) == SCHEMA_VERSION
        second.close()


class TestItRefusesASecondCurrentVersion:
    """The resolver returns the first CURRENT row it finds. Two of them would
    make `library.current()` non-deterministic -- and a Publisher packet built
    from the wrong one is wrong in a way nobody would notice."""

    def test_one_object_code_may_not_hold_two_current_versions(self, catalog):
        _object(catalog)
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, version=2)

    def test_superseding_the_first_makes_room_for_the_second(self, catalog):
        _object(catalog)
        catalog.execute("UPDATE library_object SET status = 'SUPERSEDED' WHERE version = 1")
        _object(catalog, version=2, supersedes_version=1)

        statuses = dict(
            catalog.execute("SELECT version, status FROM library_object ORDER BY version")
        )
        assert statuses == {1: "SUPERSEDED", 2: "CURRENT"}

    def test_many_superseded_versions_are_fine(self, catalog):
        for version in range(1, 6):
            catalog.execute("UPDATE library_object SET status = 'SUPERSEDED'")
            _object(catalog, version=version)
        assert catalog.execute(
            "SELECT count(*) AS n FROM library_object WHERE status = 'SUPERSEDED'"
        ).fetchone()["n"] == 4


class TestItRefusesTwoObjectsOnOneShelfFile:
    """Better refused at write time than discovered by a packet that resolves
    the same document under two names."""

    def test_two_current_objects_may_not_claim_the_same_file(self, catalog):
        _object(catalog, relative_path="Templates/closeout.md")
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, object_code="DOC-2", relative_path="Templates/closeout.md")

    def test_a_superseded_version_may_keep_its_path(self, catalog):
        """Version history is the point of a Library. A superseded version that
        had to give up its path would lose the record of what it pointed at."""
        _object(catalog, relative_path="Templates/closeout.md")
        catalog.execute("UPDATE library_object SET status = 'SUPERSEDED'")
        _object(catalog, version=2, relative_path="Templates/closeout.md")
        assert catalog.execute(
            "SELECT count(*) AS n FROM library_object WHERE relative_path = 'Templates/closeout.md'"
        ).fetchone()["n"] == 2

    def test_objects_with_no_file_do_not_collide(self, catalog):
        """An inline body is not a shelf file, and NULL is not a duplicate of
        NULL. Any number of objects may have no path at all."""
        _object(catalog, relative_path=None)
        _object(catalog, object_code="DOC-2", relative_path=None)
        _object(catalog, object_code="DOC-3", relative_path=None)
        assert catalog.execute("SELECT count(*) AS n FROM library_object").fetchone()["n"] == 3


class TestItRefusesASystemIdentityAsAnApproval:
    """Hard Rule: no authority bypass. A system may not stand as the human who
    accepted a document, under its own name or a lowercase one."""

    @pytest.mark.parametrize(
        "identity", ["INTELLIGENCE", "PUBLISHER", "LIBRARY", "SYSTEM", "AUTOMATION"]
    )
    def test_no_system_identity_may_accept_an_object(self, catalog, identity):
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, accepted_by=identity)

    @pytest.mark.parametrize("identity", ["publisher", "  Publisher  ", "sYsTeM"])
    def test_case_and_padding_do_not_get_around_it(self, catalog, identity):
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, accepted_by=identity)

    def test_an_empty_approval_is_refused(self, catalog):
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, accepted_by="")

    def test_a_real_person_is_accepted(self, catalog):
        _object(catalog, accepted_by="Mike Zachary")
        assert catalog.execute(
            "SELECT accepted_by FROM library_object"
        ).fetchone()["accepted_by"] == "Mike Zachary"

    def test_a_version_number_must_be_positive(self, catalog):
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, version=0)


class TestItRefusesAnApprovalWithNobodyBehindIt:
    def test_a_pending_candidate_may_not_carry_a_reviewer(self, catalog):
        """A reviewer on a pending candidate means one of the two fields is a
        lie, and there is no way to tell which."""
        with pytest.raises(sqlite3.IntegrityError):
            _candidate(catalog, status="PENDING_REVIEW", reviewed_by="Mike Zachary")

    @pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
    def test_a_decided_candidate_must_carry_one(self, catalog, status):
        with pytest.raises(sqlite3.IntegrityError):
            _candidate(catalog, status=status, reviewed_by=None)

    def test_a_submitter_may_not_approve_its_own_candidate(self, catalog):
        with pytest.raises(sqlite3.IntegrityError):
            _candidate(catalog, submitted_by="INTELLIGENCE", status="APPROVED",
                       reviewed_by="INTELLIGENCE")

    @pytest.mark.parametrize("identity", ["PUBLISHER", "LIBRARY", "SYSTEM", "AUTOMATION"])
    def test_no_system_identity_may_review_a_candidate(self, catalog, identity):
        with pytest.raises(sqlite3.IntegrityError):
            _candidate(catalog, submitted_by="INTELLIGENCE", status="APPROVED",
                       reviewed_by=identity)

    def test_a_human_review_is_accepted(self, catalog):
        _candidate(catalog, status="APPROVED", reviewed_by="Mike Zachary")
        assert catalog.execute(
            "SELECT reviewed_by FROM library_candidate"
        ).fetchone()["reviewed_by"] == "Mike Zachary"

    def test_a_pending_candidate_with_no_reviewer_is_accepted(self, catalog):
        _candidate(catalog)
        assert catalog.execute(
            "SELECT count(*) AS n FROM library_candidate WHERE status = 'PENDING_REVIEW'"
        ).fetchone()["n"] == 1


class TestItRefusesAnArchiveDispositionWithNoName:
    """The queue prepares Mike's Keep/Delete decision. A disposition with
    nobody behind it is not a decision, it is an accident."""

    @pytest.fixture()
    def queued(self, catalog):
        _object(catalog, status="SUPERSEDED")
        return catalog

    @pytest.mark.parametrize("disposition", ["KEEP", "DELETE"])
    def test_a_decision_requires_a_decider(self, queued, disposition):
        with pytest.raises(sqlite3.IntegrityError):
            queued.execute(
                "INSERT INTO archive_review_queue (object_code, version, queued_at, disposition) "
                "VALUES ('DOC-1', 1, '2026-09-13', ?)",
                (disposition,),
            )

    def test_a_pending_entry_may_not_carry_one(self, queued):
        with pytest.raises(sqlite3.IntegrityError):
            queued.execute(
                "INSERT INTO archive_review_queue "
                "(object_code, version, queued_at, disposition, decided_by) "
                "VALUES ('DOC-1', 1, '2026-09-13', 'PENDING', 'Mike Zachary')"
            )

    def test_a_named_decision_is_accepted(self, queued):
        queued.execute(
            "INSERT INTO archive_review_queue "
            "(object_code, version, queued_at, disposition, decided_by, decided_at) "
            "VALUES ('DOC-1', 1, '2026-09-13', 'KEEP', 'Mike Zachary', '2026-09-14')"
        )
        assert queued.execute(
            "SELECT decided_by FROM archive_review_queue"
        ).fetchone()["decided_by"] == "Mike Zachary"

    def test_it_may_not_queue_a_version_that_does_not_exist(self, queued):
        """A foreign key, enforced because open_catalog turns foreign keys on."""
        with pytest.raises(sqlite3.IntegrityError):
            queued.execute(
                "INSERT INTO archive_review_queue (object_code, version, queued_at) "
                "VALUES ('DOC-NOPE', 7, '2026-09-13')"
            )

    def test_removing_a_version_removes_its_queue_entry(self, queued):
        queued.execute(
            "INSERT INTO archive_review_queue (object_code, version, queued_at) "
            "VALUES ('DOC-1', 1, '2026-09-13')"
        )
        queued.execute("DELETE FROM library_object WHERE object_code = 'DOC-1'")
        assert queued.execute(
            "SELECT count(*) AS n FROM archive_review_queue"
        ).fetchone()["n"] == 0


class TestTheVocabularyIsClosed:
    """Status and source words are the Dispatch vocabulary. A synonym written
    into the database would be a word no reader of this program knows."""

    @pytest.mark.parametrize("status", ["current", "ACTIVE", "LIVE", "", "PENDING"])
    def test_only_the_three_object_statuses_are_accepted(self, catalog, status):
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, status=status)

    @pytest.mark.parametrize("source", ["human", "MIKE", "IMPORTED", ""])
    def test_only_the_two_sources_are_accepted(self, catalog, source):
        with pytest.raises(sqlite3.IntegrityError):
            _object(catalog, source=source)

    @pytest.mark.parametrize("finding", ["UNKNOWN", "ok", ""])
    def test_only_the_three_scan_findings_are_accepted(self, catalog, finding):
        catalog.execute(
            "INSERT INTO catalog_scan (started_at, memory_root) VALUES ('t', '/shelf')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            catalog.execute(
                "INSERT INTO catalog_finding (scan_id, relative_path, finding) VALUES (1, 'a', ?)",
                (finding,),
            )
