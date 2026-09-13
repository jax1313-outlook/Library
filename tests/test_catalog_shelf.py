"""The shelf, the scan, and the two things the scan must never do.

The shelf is a directory people open, edit and move things in. The catalog is
written by a program. They drift, and drift nobody notices is how a Publisher
packet gets built from a document that changed last month.

Two rules carry most of the weight here, and both are tested by their absence:
the scan never writes to the shelf, and the scan never adopts a file.
"""
from __future__ import annotations

import pytest

from dispatch_library.catalog import library, open_library
from dispatch_library.catalog.shelf import (
    CHANGED,
    MISSING,
    UNCATALOGUED,
    is_ignorable,
    last_scan,
    findings_of,
    sha256_of,
    walk_shelf,
)


@pytest.fixture()
def shelf(tmp_path):
    """A shelf with two documents on it."""
    root = tmp_path / "Memory"
    (root / "Templates").mkdir(parents=True)
    (root / "Templates" / "closeout.md").write_text("CLOSEOUT {load_id}\n", encoding="utf-8")
    (root / "Templates" / "delivered.md").write_text("Delivered.\n", encoding="utf-8")
    return root


@pytest.fixture()
def lib(tmp_path, shelf):
    with library(tmp_path / "catalog.db", memory_root=shelf) as service:
        yield service


def _snapshot(root):
    """Every file under root with its bytes and mtime -- for proving nothing moved."""
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestPlacingAFile:
    def test_a_placed_file_becomes_a_current_object(self, lib):
        obj = lib.place_file(
            "TPL-CLOSEOUT", "Templates", "Broker closeout",
            "Templates/closeout.md", "Mike Zachary",
        )
        assert obj.version == 1
        assert obj.body_or_uri == "Templates/closeout.md"
        assert lib.current("TPL-CLOSEOUT").accepted_by == "Mike Zachary"

    def test_the_catalog_points_at_the_file_rather_than_copying_it(self, lib, shelf):
        """A second copy in the catalog is a copy that can fall out of date."""
        lib.place_file(
            "TPL-CLOSEOUT", "Templates", "t", "Templates/closeout.md", "Mike Zachary"
        )
        entry = lib.registry.shelf_entry("TPL-CLOSEOUT", 1)
        assert entry["relative_path"] == "Templates/closeout.md"
        assert entry["content_sha256"] == sha256_of(shelf / "Templates" / "closeout.md")
        assert entry["size_bytes"] == (shelf / "Templates" / "closeout.md").stat().st_size

    def test_placing_a_file_does_not_touch_the_shelf(self, lib, shelf):
        before = _snapshot(shelf)
        lib.place_file(
            "TPL-CLOSEOUT", "Templates", "t", "Templates/closeout.md", "Mike Zachary"
        )
        assert _snapshot(shelf) == before

    def test_the_bytes_can_be_read_back(self, lib):
        lib.place_file(
            "TPL-CLOSEOUT", "Templates", "t", "Templates/closeout.md", "Mike Zachary"
        )
        assert lib.read_file("TPL-CLOSEOUT") == "CLOSEOUT {load_id}\n"

    def test_a_system_identity_may_not_place_a_file(self, lib):
        """The same rule as any other acceptance. A file on disk is not an
        approval."""
        with pytest.raises(ValueError, match="not a system identity"):
            lib.place_file(
                "TPL-CLOSEOUT", "Templates", "t", "Templates/closeout.md", "PUBLISHER"
            )

    def test_a_file_that_is_not_there_is_refused(self, lib):
        with pytest.raises(ValueError, match="no file at"):
            lib.place_file(
                "TPL-NOPE", "Templates", "t", "Templates/missing.md", "Mike Zachary"
            )

    def test_two_objects_may_not_claim_one_file(self, lib):
        import sqlite3

        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        with pytest.raises(sqlite3.IntegrityError):
            lib.place_file("TPL-B", "Templates", "t", "Templates/closeout.md", "Mike Zachary")

    def test_a_library_with_no_shelf_refuses_file_work(self, tmp_path):
        """The true answer on a machine where the shelf is not mounted."""
        with library(tmp_path / "catalog.db") as unbound:
            with pytest.raises(ValueError, match="not bound to a shelf"):
                unbound.place_file("X", "Templates", "t", "a.md", "Mike Zachary")
            with pytest.raises(ValueError, match="not bound to a shelf"):
                unbound.scan_shelf()
            # Inline bodies still work. It is a Library, just not a shelf.
            unbound.ingest_human_document(
                object_code="DOC-INLINE", collection="Reference", title="t",
                body_or_uri="the body itself", accepted_by="Mike Zachary",
            )
            assert unbound.current("DOC-INLINE") is not None

    def test_reading_an_object_with_no_file_is_none(self, lib):
        lib.ingest_human_document(
            object_code="DOC-INLINE", collection="Reference", title="t",
            body_or_uri="inline", accepted_by="Mike Zachary",
        )
        assert lib.read_file("DOC-INLINE") is None

    def test_reading_an_unknown_object_is_none(self, lib):
        assert lib.read_file("DOC-NOPE") is None

    def test_reading_a_vanished_file_raises_rather_than_returning_none(self, lib, shelf):
        """None would make a missing document look like an object that never
        had one. Those are different problems and need different answers."""
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").unlink()
        with pytest.raises(FileNotFoundError, match="not on the shelf"):
            lib.read_file("TPL-A")


class TestTheScanReports:
    def test_a_file_nobody_catalogued_is_reported_not_adopted(self, lib):
        """The rule that matters most. A program that catalogued files it found
        would be manufacturing approvals by walking a directory."""
        result = lib.scan_shelf()

        assert {f.relative_path for f in result.uncatalogued} == {
            "Templates/closeout.md", "Templates/delivered.md"
        }
        assert lib.registry.all_object_codes() == [], "the scan adopted something"

    def test_a_catalogued_file_produces_no_finding(self, lib):
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        lib.place_file("TPL-B", "Templates", "t", "Templates/delivered.md", "Mike Zachary")

        result = lib.scan_shelf()
        assert result.clean
        assert result.files_seen == 2
        assert result.catalogued == 2

    def test_an_edited_file_is_reported_as_changed(self, lib, shelf):
        """Somebody opening the file in Explorer and saving it. This is the
        drift the hash exists to catch."""
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").write_text("EDITED BY HAND\n", encoding="utf-8")

        result = lib.scan_shelf()
        assert [f.relative_path for f in result.changed] == ["Templates/closeout.md"]
        assert "TPL-A v1" in result.changed[0].detail

    def test_a_vanished_file_is_reported_and_the_object_is_kept(self, lib, shelf):
        """MISSING is a defect, not a deletion. Library does not quietly forget
        an object because a file moved."""
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").unlink()

        result = lib.scan_shelf()
        assert [f.relative_path for f in result.missing] == ["Templates/closeout.md"]
        assert lib.current("TPL-A") is not None, "the scan deleted a Library object"

    def test_all_three_findings_can_appear_at_once(self, lib, shelf):
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        lib.place_file("TPL-B", "Templates", "t", "Templates/delivered.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").write_text("edited\n", encoding="utf-8")
        (shelf / "Templates" / "delivered.md").unlink()
        (shelf / "Templates" / "new.md").write_text("brand new\n", encoding="utf-8")

        result = lib.scan_shelf()
        assert len(result.changed) == 1
        assert len(result.missing) == 1
        assert len(result.uncatalogued) == 1

    def test_a_superseded_version_is_not_scanned(self, lib, shelf):
        """The scan checks what is current. A superseded version points at what
        the document used to be, and reporting it as CHANGED every time would
        make the report useless."""
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").write_text("version two\n", encoding="utf-8")
        lib.place_file("TPL-A", "Templates", "t2", "Templates/closeout.md", "Mike Zachary")

        result = lib.scan_shelf()
        assert result.changed == []
        assert lib.registry.get_version("TPL-A", 1).status.value == "SUPERSEDED"


class TestTheScanNeverWritesToTheShelf:
    def test_scanning_leaves_every_file_byte_for_byte(self, lib, shelf):
        before = _snapshot(shelf)
        lib.scan_shelf()
        assert _snapshot(shelf) == before

    def test_scanning_a_shelf_with_findings_still_writes_nothing(self, lib, shelf):
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").write_text("edited\n", encoding="utf-8")
        before = _snapshot(shelf)

        lib.scan_shelf()
        assert _snapshot(shelf) == before

    def test_it_does_not_create_a_shelf_that_is_not_there(self, tmp_path):
        """A scan that made the directory it was looking for would report a
        clean empty shelf where the truth is that the shelf is not mounted."""
        absent = tmp_path / "not-mounted"
        with library(tmp_path / "catalog.db", memory_root=absent) as lib:
            result = lib.scan_shelf()
            assert result.files_seen == 0
        assert not absent.exists()


class TestTheScanIsIdempotent:
    def test_two_scans_of_an_unchanged_shelf_agree(self, lib):
        first = lib.scan_shelf()
        second = lib.scan_shelf()
        assert [(f.relative_path, f.finding) for f in first.findings] == \
               [(f.relative_path, f.finding) for f in second.findings]

    def test_a_clean_shelf_stays_clean_however_often_it_is_scanned(self, lib):
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        lib.place_file("TPL-B", "Templates", "t", "Templates/delivered.md", "Mike Zachary")
        for _ in range(3):
            assert lib.scan_shelf().clean

    def test_findings_come_back_in_a_stable_order(self, lib, shelf):
        """A report whose lines move between runs is a report nobody can diff."""
        for name in ("c.md", "a.md", "b.md"):
            (shelf / "Templates" / name).write_text(name, encoding="utf-8")
        paths = [f.relative_path for f in lib.scan_shelf(record=False).uncatalogued]
        assert paths == sorted(paths)


class TestTheDryRun:
    def test_it_finds_exactly_what_the_recording_scan_finds(self, lib, shelf):
        (shelf / "Templates" / "extra.md").write_text("x", encoding="utf-8")
        dry = lib.scan_shelf(record=False)
        wet = lib.scan_shelf(record=True)
        assert [(f.relative_path, f.finding) for f in dry.findings] == \
               [(f.relative_path, f.finding) for f in wet.findings]

    def test_it_writes_no_scan_record(self, lib):
        result = lib.scan_shelf(record=False)
        assert result.scan_id is None
        assert last_scan(lib.connection) is None

    def test_it_writes_nothing_to_the_shelf_either(self, lib, shelf):
        before = _snapshot(shelf)
        lib.scan_shelf(record=False)
        assert _snapshot(shelf) == before


class TestDriftIsARecord:
    def test_a_scan_is_written_down_with_its_counts(self, lib, shelf):
        lib.place_file("TPL-A", "Templates", "t", "Templates/closeout.md", "Mike Zachary")
        (shelf / "Templates" / "closeout.md").write_text("edited\n", encoding="utf-8")

        result = lib.scan_shelf()
        record = last_scan(lib.connection)
        assert record["scan_id"] == result.scan_id
        assert record["files_seen"] == 2
        assert record["catalogued"] == 1
        assert record["changed"] == 1
        assert record["uncatalogued"] == 1
        assert record["memory_root"] == str(shelf)
        assert record["finished_at"] is not None

    def test_the_findings_are_readable_afterwards(self, lib):
        result = lib.scan_shelf()
        stored = findings_of(lib.connection, result.scan_id)
        assert {f.relative_path for f in stored} == {
            "Templates/closeout.md", "Templates/delivered.md"
        }
        assert all(f.finding == UNCATALOGUED for f in stored)

    def test_a_history_of_scans_accumulates(self, lib):
        ids = [lib.scan_shelf().scan_id for _ in range(3)]
        assert len(set(ids)) == 3
        count = lib.connection.execute(
            "SELECT count(*) AS n FROM catalog_scan"
        ).fetchone()["n"]
        assert count == 3

    def test_scan_records_survive_a_restart(self, tmp_path, shelf):
        path = tmp_path / "catalog.db"
        with library(path, memory_root=shelf) as first:
            scan_id = first.scan_shelf().scan_id
        with library(path, memory_root=shelf) as second:
            assert len(findings_of(second.connection, scan_id)) == 2


class TestWhatTheScanIgnores:
    @pytest.mark.parametrize("name", [
        ".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep", "notes.tmp", "x.swp",
    ])
    def test_operating_system_litter_is_not_a_finding(self, lib, shelf, name):
        """A scan that reported these would bury the findings that matter."""
        (shelf / name).write_text("junk", encoding="utf-8")
        assert name not in {f.relative_path for f in lib.scan_shelf().uncatalogued}

    def test_a_git_directory_is_skipped_whole(self, lib, shelf):
        (shelf / ".git" / "objects").mkdir(parents=True)
        (shelf / ".git" / "objects" / "abc123").write_text("blob", encoding="utf-8")
        assert not any(".git" in f.relative_path for f in lib.scan_shelf().findings)

    def test_a_real_document_in_a_nested_folder_is_still_found(self, lib, shelf):
        deep = shelf / "Compliance" / "2026" / "Q3"
        deep.mkdir(parents=True)
        (deep / "policy.md").write_text("policy", encoding="utf-8")
        assert "Compliance/2026/Q3/policy.md" in {
            f.relative_path for f in lib.scan_shelf().uncatalogued
        }

    def test_is_ignorable_names_what_it_skips(self):
        assert is_ignorable(__import__("pathlib").Path(".git/config"))
        assert is_ignorable(__import__("pathlib").Path("Templates/.DS_Store"))
        assert not is_ignorable(__import__("pathlib").Path("Templates/closeout.md"))

    def test_walking_a_shelf_that_is_not_there_is_empty_not_an_error(self, tmp_path):
        assert list(walk_shelf(tmp_path / "nope")) == []
