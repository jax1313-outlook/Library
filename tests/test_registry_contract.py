"""One suite, run against both registries.

`LibraryService` takes a registry by injection, which is only useful if the
two implementations actually answer the same way. Two separate test files
would let them drift apart while both stayed green; this one cannot.

Every test below runs twice -- once against the in-memory `ObjectRegistry`,
once against `SqliteObjectRegistry` over a real catalog file.
"""
from __future__ import annotations

import pytest

from dispatch_library import ingestion, resolver
from dispatch_library.catalog import open_catalog
from dispatch_library.catalog.registry import SqliteObjectRegistry
from dispatch_library.models import (
    LibraryObject,
    LibraryObjectSource,
    LibraryObjectStatus,
)
from dispatch_library.registry import ObjectRegistry


@pytest.fixture(params=["memory", "sqlite"])
def registry(request, tmp_path):
    if request.param == "memory":
        yield ObjectRegistry()
        return
    connection = open_catalog(tmp_path / "catalog.db")
    yield SqliteObjectRegistry(connection)
    connection.close()


def _obj(object_code, version, status=LibraryObjectStatus.CURRENT, **overrides):
    kwargs = dict(
        object_code=object_code,
        collection="Reference",
        title=f"Title v{version}",
        version=version,
        status=status,
        source=LibraryObjectSource.HUMAN_PLACED,
        body_or_uri="body",
        accepted_by="Mike Zachary",
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
        assert statuses == {
            1: LibraryObjectStatus.SUPERSEDED,
            2: LibraryObjectStatus.CURRENT,
        }

    def test_there_is_never_more_than_one_current_version(self, registry):
        for version in range(1, 8):
            registry.add_version(_obj("DOC-1", version))
        current = [
            o for o in registry.history("DOC-1")
            if o.status == LibraryObjectStatus.CURRENT
        ]
        assert len(current) == 1
        assert current[0].version == 7

    def test_superseding_one_code_leaves_another_alone(self, registry):
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-2", 1))
        registry.add_version(_obj("DOC-1", 2, supersedes_version=1))

        assert resolver.current(registry, "DOC-2").version == 1
        assert resolver.current(registry, "DOC-2").status == LibraryObjectStatus.CURRENT

    def test_a_draft_candidate_version_supersedes_nothing(self, registry):
        """Only a CURRENT version displaces the current one. A draft is not
        truth yet, and adding one must not quietly retire what is."""
        registry.add_version(_obj("DOC-1", 1))
        registry.add_version(_obj("DOC-1", 2, status=LibraryObjectStatus.DRAFT_CANDIDATE))

        assert resolver.current(registry, "DOC-1").version == 1


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
        registry.add_version(_obj("DOC-1", 1, collection="Templates"))
        registry.add_version(_obj("DOC-2", 1, collection="Reference"))

        assert [o.object_code for o in resolver.list_current(registry, "Templates")] == ["DOC-1"]


class TestIngestionWorksAgainstBoth:
    """`ingestion.py` is untouched by the persistence work. These prove it."""

    def test_a_human_placed_document_is_current_immediately(self, registry):
        obj = ingestion.ingest_human_document(
            registry, "TPL-1", "Templates", "A template", "body", "Mike Zachary"
        )
        assert obj.status == LibraryObjectStatus.CURRENT
        assert obj.source == LibraryObjectSource.HUMAN_PLACED
        assert resolver.current(registry, "TPL-1").version == 1

    def test_placing_it_again_makes_version_two(self, registry):
        ingestion.ingest_human_document(
            registry, "TPL-1", "Templates", "v1", "body one", "Mike Zachary"
        )
        second = ingestion.ingest_human_document(
            registry, "TPL-1", "Templates", "v2", "body two", "Mike Zachary"
        )
        assert second.version == 2
        assert second.supersedes_version == 1
        assert resolver.current(registry, "TPL-1").body_or_uri == "body two"

    def test_a_system_identity_may_not_place_a_document(self, registry):
        with pytest.raises(ValueError, match="not a system identity"):
            ingestion.ingest_human_document(
                registry, "TPL-1", "Templates", "t", "body", "PUBLISHER"
            )

    def test_an_invalid_collection_is_refused(self, registry):
        with pytest.raises(ValueError, match="not one of the 15"):
            ingestion.ingest_human_document(
                registry, "TPL-1", "Invented", "t", "body", "Mike Zachary"
            )

    def test_an_approved_candidate_lands_in_either_registry(self, registry):
        from dispatch_library.models import LibraryCandidate, SubmittedBy

        queue = ingestion.CandidateQueue()
        candidate = ingestion.submit_candidate(queue, LibraryCandidate(
            submitted_by=SubmittedBy.INTELLIGENCE,
            source_type="finding",
            collection="Reference",
            proposed_object_code="DOC-FROM-INTEL",
            proposed_title="A finding worth keeping",
            proposed_body_or_reference="body",
        ))
        ingestion.review_candidate(
            queue, registry, candidate.candidate_id, approve=True, reviewed_by="Mike Zachary"
        )
        placed = resolver.current(registry, "DOC-FROM-INTEL")
        assert placed is not None
        assert placed.source == LibraryObjectSource.APPROVED_CANDIDATE
        assert placed.accepted_by == "Mike Zachary"


class TestPersistence:
    """The whole point of S1-S2: the answers outlive the process."""

    def test_a_catalog_remembers_across_connections(self, tmp_path):
        path = tmp_path / "catalog.db"

        first = open_catalog(path)
        ingestion.ingest_human_document(
            SqliteObjectRegistry(first), "TPL-BROKER-CLOSEOUT", "Templates",
            "Broker closeout notice", "Templates/closeout.md", "Mike Zachary",
            ["closeout"],
        )
        first.close()

        second = open_catalog(path)
        registry = SqliteObjectRegistry(second)
        obj = resolver.current(registry, "TPL-BROKER-CLOSEOUT")
        assert obj is not None
        assert obj.title == "Broker closeout notice"
        assert obj.accepted_by == "Mike Zachary"
        assert obj.tags == ["closeout"]
        second.close()

    def test_version_history_outlives_the_process(self, tmp_path):
        path = tmp_path / "catalog.db"
        for body in ("one", "two", "three"):
            connection = open_catalog(path)
            ingestion.ingest_human_document(
                SqliteObjectRegistry(connection), "DOC-1", "Reference", "t", body,
                "Mike Zachary",
            )
            connection.close()

        connection = open_catalog(path)
        registry = SqliteObjectRegistry(connection)
        assert [o.version for o in registry.history("DOC-1")] == [1, 2, 3]
        assert resolver.current(registry, "DOC-1").body_or_uri == "three"
        connection.close()

    def test_the_dict_registry_forgets_and_that_is_the_difference(self):
        """Stated as a test so the limitation is a fact rather than a claim.
        This is what Phase A ran into: the shelf emptied when the process did."""
        registry = ObjectRegistry()
        ingestion.ingest_human_document(
            registry, "DOC-1", "Reference", "t", "body", "Mike Zachary"
        )
        assert resolver.current(registry, "DOC-1") is not None
        assert resolver.current(ObjectRegistry(), "DOC-1") is None


class TestTheOneDifferenceBetweenThem:
    def test_the_difference_from_the_dict_registry(self, tmp_path):
        """`ObjectRegistry` supersedes by mutating the Python object a caller
        still holds. A database row cannot reach into a caller's variable.

        Both registries give the same answer when asked -- `history()` and
        `current()` agree -- so no code that reads the registry can tell them
        apart. Only code holding a stale instance can, and this test says so
        out loud rather than leaving someone to find it.
        """
        memory = ObjectRegistry()
        v1_memory = memory.add_version(_obj("DOC-1", 1))
        memory.add_version(_obj("DOC-1", 2, supersedes_version=1))

        connection = open_catalog(tmp_path / "catalog.db")
        sqlite_registry = SqliteObjectRegistry(connection)
        v1_sqlite = sqlite_registry.add_version(_obj("DOC-1", 1))
        sqlite_registry.add_version(_obj("DOC-1", 2, supersedes_version=1))

        # The held instance: they differ.
        assert v1_memory.status == LibraryObjectStatus.SUPERSEDED
        assert v1_sqlite.status == LibraryObjectStatus.CURRENT, "the stale instance"

        # Asked properly: they agree, and the catalog is right.
        assert sqlite_registry.get_version("DOC-1", 1).status == LibraryObjectStatus.SUPERSEDED
        assert memory.get_version("DOC-1", 1).status == LibraryObjectStatus.SUPERSEDED
        connection.close()


class TestSupersessionIsAtomic:
    """S3. On disk, the window between the flip and the insert is real."""

    def test_a_failed_insert_leaves_the_previous_version_current(self, tmp_path):
        """The flip must not survive an insert that never lands. Otherwise the
        catalog holds no CURRENT version at all and `current()` returns None
        for a document that is sitting right there."""
        connection = open_catalog(tmp_path / "catalog.db")
        registry = SqliteObjectRegistry(connection)
        registry.add_version(_obj("DOC-1", 1))

        # Version 1 again: the insert violates the primary key and rolls back.
        with pytest.raises(Exception):
            registry.add_version(_obj("DOC-1", 1, title="collides"))

        survivor = resolver.current(registry, "DOC-1")
        assert survivor is not None, "the flip was committed without its insert"
        assert survivor.version == 1
        assert survivor.title == "Title v1"
        connection.close()

    def test_the_database_refuses_a_second_current_even_if_the_code_is_wrong(self, tmp_path):
        """Second line of defence. If add_version is ever rewritten to do the
        two writes apart, the partial unique index refuses the result rather
        than letting the catalog hold a state the resolver cannot read."""
        import sqlite3

        connection = open_catalog(tmp_path / "catalog.db")
        registry = SqliteObjectRegistry(connection)
        registry.add_version(_obj("DOC-1", 1))

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO library_object (object_code, version, collection, title, "
                "status, source, body_or_uri, accepted_by, accepted_at) "
                "VALUES ('DOC-1', 2, 'Reference', 't', 'CURRENT', 'HUMAN_PLACED', "
                "'b', 'Mike Zachary', 't')"
            )
        connection.close()
