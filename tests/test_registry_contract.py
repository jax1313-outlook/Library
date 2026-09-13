"""One suite, run against both registries.

`LibraryService` takes a registry by injection, which is only useful if the two implementations
actually answer the same way. Every test in the shared classes runs twice -- once against the
in-memory `ObjectRegistry`, once against `SqliteObjectRegistry` over a real catalog file.

Where catalog schema version 2 is deliberately stricter than the dict, the difference is stated in
`TestWhereTheCatalogIsStricter` rather than hidden behind a skipped test.
"""
from __future__ import annotations

import sqlite3

import pytest

from dispatch_library import ingestion, resolver
from dispatch_library.catalog import Catalog, CatalogRefusal, MissingObjectType, open_catalog
from dispatch_library.catalog.registry import SqliteObjectRegistry
from dispatch_library.models import (
    LibraryCandidate,
    LibraryObject,
    LibraryObjectSource,
    LibraryObjectStatus,
    SubmittedBy,
)
from dispatch_library.registry import ObjectRegistry

APPROVER = "Certification Operator"


@pytest.fixture(params=["memory", "sqlite"])
def registry(request, tmp_path):
    if request.param == "memory":
        yield ObjectRegistry()
        return
    connection = open_catalog(tmp_path / "catalog.db")
    yield SqliteObjectRegistry(Catalog(connection))
    connection.close()


def _sqlite(tmp_path):
    connection = open_catalog(tmp_path / "catalog.db")
    return connection, SqliteObjectRegistry(Catalog(connection))


def _obj(object_code, version, status=LibraryObjectStatus.CURRENT, **overrides):
    kwargs = dict(
        object_code=object_code,
        collection="Reference",
        title=f"Title v{version}",
        version=version,
        status=status,
        source=LibraryObjectSource.HUMAN_PLACED,
        body_or_uri="body",
        accepted_by=APPROVER,
        object_type="CONTROLLED_COMPANY_FACT",
    )
    kwargs.update(overrides)
    return LibraryObject(**kwargs)


class TestVersioning:
    def test_the_first_version_of_an_unknown_code_is_one(self, registry):
        assert registry.next_version("DOC-NEW") == 1

    def test_versions_count_up_from_what_is_there(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        assert registry.next_version("DOC-1") == 2
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        assert registry.next_version("DOC-1") == 3

    def test_each_code_counts_on_its_own(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        registry.add_version(_obj("DOC-2", 1))
        assert registry.next_version("DOC-1") == 3
        assert registry.next_version("DOC-2") == 2


class TestSupersession:
    def test_a_new_current_version_supersedes_the_previous_one(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        statuses = {o.version: o.status for o in registry.history("DOC-1")}
        assert statuses == {1: LibraryObjectStatus.SUPERSEDED, 2: LibraryObjectStatus.CURRENT}

    def test_there_is_never_more_than_one_current_version(self, registry):
        for version in range(1, 8):
            registry.add_version(_obj("DOC-1", version))
        current = [o for o in registry.history("DOC-1") if o.status == LibraryObjectStatus.CURRENT]
        assert len(current) == 1
        assert current[0].version == 7

    def test_superseding_one_code_leaves_another_alone(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-2", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        assert resolver.current(registry, "DOC-2").version == 1
        assert resolver.current(registry, "DOC-2").status == LibraryObjectStatus.CURRENT


class TestHistory:
    def test_history_is_oldest_first(self, registry):
        for version in (1, 2, 3):
            registry.add_version(_obj("DOC-1", version))
        assert [o.version for o in registry.history("DOC-1")] == [1, 2, 3]

    def test_an_unknown_code_has_an_empty_history(self, registry):
        assert registry.history("DOC-NOPE") == []

    def test_a_version_can_be_fetched_by_number(self, registry):
        registry.add_version(_obj("DOC-1", 1, title="First"))
        registry.add_version(_obj("DOC-1", 2, title="Second", supersedes_version=1))
        assert registry.get_version("DOC-1", 1).title == "First"
        assert registry.get_version("DOC-1", 2).title == "Second"

    def test_a_version_that_does_not_exist_is_none_not_an_error(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        assert registry.get_version("DOC-1", 99) is None
        assert registry.get_version("DOC-NOPE", 1) is None

    def test_every_code_is_listed_once_however_many_versions(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        registry.add_version(_obj("DOC-2", 1))
        assert sorted(registry.all_object_codes()) == ["DOC-1", "DOC-2"]

    def test_an_empty_registry_lists_nothing(self, registry):
        assert registry.all_object_codes() == []

    def test_tags_survive_the_round_trip(self, registry):
        registry.add_version(_obj("DOC-1", 1, tags=["closeout", "broker"]))
        assert registry.get_version("DOC-1", 1).tags == ["closeout", "broker"]

    def test_no_tags_is_an_empty_list_not_none(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        assert registry.get_version("DOC-1", 1).tags == []

    def test_supersedes_version_is_reported(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        assert registry.get_version("DOC-1", 2).supersedes_version == 1


class TestTheResolverReadsBothTheSameWay:
    def test_current_returns_the_current_version(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        assert resolver.current(registry, "DOC-1").version == 2

    def test_current_is_none_for_an_unknown_code(self, registry):
        assert resolver.current(registry, "DOC-NOPE") is None

    def test_list_current_returns_one_row_per_code(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        registry.add_version(_obj("DOC-2", 1))
        listed = resolver.list_current(registry)
        assert {(o.object_code, o.version) for o in listed} == {("DOC-1", 2), ("DOC-2", 1)}

    def test_list_current_filters_by_collection(self, registry):
        registry.add_version(_obj("DOC-1", 1, collection="Templates", object_type="FORM_TEMPLATE"))
        registry.add_version(_obj("DOC-2", 1, collection="Reference"))
        assert [o.object_code for o in resolver.list_current(registry, "Templates")] == ["DOC-1"]


class TestIngestionWorksAgainstBoth:
    def test_a_human_placed_document_is_current_immediately(self, registry):
        obj = ingestion.ingest_human_document(
            registry, "TPL-1", "Templates", "A template", "body", APPROVER, object_type="FORM_TEMPLATE")
        assert obj.status == LibraryObjectStatus.CURRENT
        assert obj.source == LibraryObjectSource.HUMAN_PLACED
        assert resolver.current(registry, "TPL-1").version == 1

    def test_placing_it_again_makes_version_two(self, registry):
        ingestion.ingest_human_document(registry, "TPL-1", "Templates", "v1", "body one", APPROVER,
                                        object_type="FORM_TEMPLATE")
        second = ingestion.ingest_human_document(registry, "TPL-1", "Templates", "v2", "body two", APPROVER,
                                                 object_type="FORM_TEMPLATE")
        assert second.version == 2
        assert second.supersedes_version == 1
        assert resolver.current(registry, "TPL-1").body_or_uri == "body two"

    @pytest.mark.parametrize("who", ["PUBLISHER", "Joe", "Email Helper", "email-helper", " comi ", "Dispatch"])
    def test_a_system_identity_may_not_place_a_document(self, registry, who):
        with pytest.raises(ValueError, match="not a system identity"):
            ingestion.ingest_human_document(registry, "TPL-1", "Templates", "t", "body", who,
                                            object_type="FORM_TEMPLATE")

    def test_an_invalid_collection_is_refused(self, registry):
        with pytest.raises(ValueError, match="not one of the 15"):
            ingestion.ingest_human_document(registry, "TPL-1", "Invented", "t", "body", APPROVER,
                                            object_type="FORM_TEMPLATE")


class TestPersistence:
    def test_a_catalog_remembers_across_connections(self, tmp_path):
        first, registry = _sqlite(tmp_path)
        ingestion.ingest_human_document(registry, "TPL-BROKER-CLOSEOUT", "Templates", "Broker closeout notice",
                                        "Closeout body", APPROVER, ["closeout"], object_type="FORM_TEMPLATE")
        first.close()

        second, registry = _sqlite(tmp_path)
        obj = resolver.current(registry, "TPL-BROKER-CLOSEOUT")
        assert (obj.title, obj.accepted_by, obj.tags, obj.object_type) == (
            "Broker closeout notice", APPROVER, ["closeout"], "FORM_TEMPLATE")
        second.close()

    def test_version_history_outlives_the_process(self, tmp_path):
        for body in ("one", "two", "three"):
            connection, registry = _sqlite(tmp_path)
            ingestion.ingest_human_document(registry, "DOC-1", "Reference", "t", body, APPROVER,
                                            object_type="CONTROLLED_COMPANY_FACT")
            connection.close()
        connection, registry = _sqlite(tmp_path)
        assert [o.version for o in registry.history("DOC-1")] == [1, 2, 3]
        assert resolver.current(registry, "DOC-1").body_or_uri == "three"
        connection.close()

    def test_the_dict_registry_forgets_and_that_is_the_difference(self):
        registry = ObjectRegistry()
        ingestion.ingest_human_document(registry, "DOC-1", "Reference", "t", "body", APPROVER)
        assert resolver.current(registry, "DOC-1") is not None
        assert resolver.current(ObjectRegistry(), "DOC-1") is None


class TestWhereTheCatalogIsStricter:
    """Plan v2 rules the dict never had. Each is a refusal in the catalog, on purpose."""

    def test_object_type_is_required_and_a_notice_records_the_refusal(self, tmp_path):
        connection, registry = _sqlite(tmp_path)
        with pytest.raises(MissingObjectType) as refused:
            ingestion.ingest_human_document(registry, "TPL-1", "Templates", "t", "body", APPROVER)
        notice = connection.execute("SELECT * FROM library_notice WHERE notice_id = ?",
                                    (refused.value.notice_id,)).fetchone()
        assert (notice["notice_type"], notice["missing_field"], notice["status"]) == (
            "MISSING_FIELD", "object_type", "OPEN")
        assert registry.all_object_codes() == []
        connection.close()

    def test_the_dict_registry_accepts_the_same_call_without_a_type(self):
        registry = ObjectRegistry()
        assert ingestion.ingest_human_document(registry, "TPL-1", "Templates", "t", "body", APPROVER).object_type is None

    def test_a_draft_is_a_candidate_not_a_version(self, tmp_path):
        connection, registry = _sqlite(tmp_path)
        registry.add_version(_obj("DOC-1", 1))
        with pytest.raises(CatalogRefusal, match="draft is a Library candidate"):
            registry.add_version(_obj("DOC-1", 2, status=LibraryObjectStatus.DRAFT_CANDIDATE))
        assert resolver.current(registry, "DOC-1").version == 1
        connection.close()

    def test_an_approved_candidate_is_written_by_review_not_add_version(self, tmp_path):
        connection, registry = _sqlite(tmp_path)
        queue = ingestion.CandidateQueue()
        candidate = ingestion.submit_candidate(queue, LibraryCandidate(
            submitted_by=SubmittedBy.INTELLIGENCE, source_type="finding", collection="Reference",
            proposed_object_code="DOC-FROM-INTEL", proposed_title="A finding", proposed_body_or_reference="body"))
        with pytest.raises(CatalogRefusal, match="review_candidate"):
            ingestion.review_candidate(queue, registry, candidate.candidate_id, approve=True, reviewed_by=APPROVER)
        assert resolver.current(registry, "DOC-FROM-INTEL") is None
        connection.close()

    def test_a_held_instance_is_updated_on_the_dict_only(self, tmp_path):
        memory = ObjectRegistry()
        v1_memory = memory.add_version(_obj("DOC-1", 1))
        memory.add_version(_obj("DOC-1", 2, supersedes_version=1))
        connection, sqlite_registry = _sqlite(tmp_path)
        v1_sqlite = sqlite_registry.add_version(_obj("DOC-1", 1))
        sqlite_registry.add_version(_obj("DOC-1", 2, supersedes_version=1))
        assert v1_memory.status == LibraryObjectStatus.SUPERSEDED
        assert v1_sqlite.status == LibraryObjectStatus.CURRENT, "the stale instance"
        assert sqlite_registry.get_version("DOC-1", 1).status == LibraryObjectStatus.SUPERSEDED
        connection.close()


class TestSupersessionIsAtomic:
    def test_a_failed_insert_leaves_the_previous_version_current(self, tmp_path):
        connection, registry = _sqlite(tmp_path)
        registry.add_version(_obj("DOC-1", 1))
        with pytest.raises(CatalogRefusal):
            registry.add_version(_obj("DOC-1", 1, title="collides"))
        survivor = resolver.current(registry, "DOC-1")
        assert survivor is not None, "the flip was committed without its insert"
        assert (survivor.version, survivor.title) == (1, "Title v1")
        connection.close()

    def test_the_database_refuses_a_second_current_even_if_the_code_is_wrong(self, tmp_path):
        connection, registry = _sqlite(tmp_path)
        registry.add_version(_obj("DOC-1", 1))
        object_id = connection.execute("SELECT library_object_id FROM library_object").fetchone()[0]
        connection.execute("DROP TRIGGER library_version_supersedes_correctly")
        connection.execute("BEGIN")
        connection.execute(
            "INSERT INTO approval_record (approval_record_id, library_object_id, version_id, approver, "
            "approval_status, approval_basis, approved_at) VALUES ('apr_x', ?, 'libver_x', 'Someone', "
            "'APPROVED', 'HUMAN_PLACED', 't')", (object_id,))
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            connection.execute(
                "INSERT INTO library_version (version_id, library_object_id, version_major, version_minor, "
                "lifecycle_state, title, content_uri, body, approval_record_id, created_at) "
                "VALUES ('libver_x', ?, 2, 0, 'CURRENT', 't', 'inline:x', 'b', 'apr_x', 't')", (object_id,))
        connection.execute("ROLLBACK")
        connection.close()
