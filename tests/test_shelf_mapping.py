import os
from pathlib import Path

import pytest

from dispatch_library.shelf_mapping import (
    MEMORY_FOLDER_MAPPING,
    PLACEMENT_CONFLICTS,
    FolderMapping,
    MappingBasis,
    PlacementConflict,
    collections_without_a_folder,
    format_report,
    map_memory_root,
    mapping_for,
)
from dispatch_library.taxonomy import COLLECTION_SET

# The eighteen top-level folders of D:\Memory as listed on 2026-09-13.
LISTED_2026_09_13 = [
    "Company Library", "Broker Library", "Customer Library", "Location Intelligence",
    "Operational Intelligence", "Forms", "Templates", "Procedures", "Manuals", "Receipts", "Fuel",
    "Compliance", "Equipment", "Drivers", "Insurance", "Certifications", "Evidence", "Documents",
]

REAL_MEMORY = Path(os.environ.get("DISPATCH_MEMORY_ROOT", r"D:\Memory"))


def test_table_covers_exactly_the_listed_folders():
    assert sorted(m.folder for m in MEMORY_FOLDER_MAPPING) == sorted(LISTED_2026_09_13)


def test_every_mapped_collection_is_one_of_the_fifteen():
    for m in MEMORY_FOLDER_MAPPING:
        assert m.collection is None or m.collection in COLLECTION_SET


def test_rows_are_exactly_the_owner_ruling_of_2026_09_13():
    rows = {m.folder: (m.basis, m.collection) for m in MEMORY_FOLDER_MAPPING}
    n, d, u = MappingBasis.NAME_MATCH, MappingBasis.DOCTRINE_SUPPORTED, MappingBasis.UNMAPPED
    assert rows == {
        "Company Library": (n, "Company"), "Broker Library": (n, "Broker"),
        "Customer Library": (n, "Customer"), "Location Intelligence": (n, "Location_Intelligence"),
        "Templates": (n, "Templates"), "Compliance": (n, "Compliance"),
        "Procedures": (d, "Process"), "Manuals": (d, "Training"), "Forms": (d, "Templates"),
        "Insurance": (d, "Company"), "Equipment": (d, "Company"), "Certifications": (d, "Compliance"),
        "Operational Intelligence": (u, None), "Receipts": (u, None), "Fuel": (u, None),
        "Drivers": (u, None), "Evidence": (u, None), "Documents": (u, None),
    }


def test_nothing_is_forced_into_reference():
    assert all(m.collection != "Reference" for m in MEMORY_FOLDER_MAPPING)


def test_doctrine_rows_cite_the_core_object_model():
    for m in MEMORY_FOLDER_MAPPING:
        if m.basis is MappingBasis.DOCTRINE_SUPPORTED:
            assert "Core Object Model" in m.citation


def test_placement_conflicts_cover_every_company_library_file_seen():
    assert len(PLACEMENT_CONFLICTS) == 16
    assert len({c.relative_path for c in PLACEMENT_CONFLICTS}) == 16
    assert all(c.relative_path.startswith("Company Library/") for c in PLACEMENT_CONFLICTS)


def test_placement_recommendations_follow_ruling_5():
    for c in PLACEMENT_CONFLICTS:
        expected = "Constitution" if c.kind == "worker constitution" else "Reference"
        assert c.recommended_collection == expected


def test_a_placement_recommendation_cannot_name_a_sixteenth_collection():
    with pytest.raises(ValueError, match="not one of the 15"):
        PlacementConflict("Company Library/x.md", "worker constitution", "Constitutions")


def test_a_sixteenth_collection_is_refused():
    with pytest.raises(ValueError, match="not one of the 15"):
        FolderMapping("Fuel", "Fuel", MappingBasis.NAME_MATCH, "folder name")


def test_unmapped_row_cannot_carry_a_collection():
    with pytest.raises(ValueError, match="no collection"):
        FolderMapping("Fuel", "Operations", MappingBasis.UNMAPPED, "no collection")


def test_lookup_is_case_insensitive():
    assert mapping_for("company library").collection == "Company"


def test_collections_without_a_folder():
    assert collections_without_a_folder() == [
        "Constitution", "Operations", "Reference", "Route_Intelligence", "Publisher_Parts",
        "Security", "Index",
    ]


def test_scan_reports_unknown_folders_and_loose_files_and_writes_nothing(tmp_path):
    (tmp_path / "Templates" / "sub").mkdir(parents=True)
    (tmp_path / "Templates" / "sub" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "Mystery").mkdir()
    (tmp_path / "loose.txt").write_text("x", encoding="utf-8")
    before = sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))

    report = map_memory_root(tmp_path)

    by_name = {f.folder: f for f in report.folders}
    assert by_name["Templates"].mapping.collection == "Templates"
    assert by_name["Templates"].file_count == 1
    assert by_name["Mystery"].mapping.basis is MappingBasis.UNMAPPED
    assert report.root_files == ("loose.txt",)
    assert "Evidence" in report.table_rows_not_on_disk
    text = format_report(report)
    assert sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*")) == before
    assert "UNMAPPED" in text
    assert "NOT FOUND" in text  # conflicts are checked against this root, not assumed present


def test_missing_root_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        map_memory_root(tmp_path / "nope")


@pytest.mark.skipif(not REAL_MEMORY.is_dir(), reason=f"{REAL_MEMORY} is not on this machine")
def test_real_memory_root_has_no_folder_outside_the_table():
    report = map_memory_root(REAL_MEMORY)
    unknown = [f.folder for f in report.folders if mapping_for(f.folder) is None]
    assert unknown == [], f"new folders under {REAL_MEMORY} need a mapping decision: {unknown}"


@pytest.mark.skipif(not REAL_MEMORY.is_dir(), reason=f"{REAL_MEMORY} is not on this machine")
def test_real_memory_root_still_holds_every_recorded_conflict():
    absent = [c.relative_path for c in PLACEMENT_CONFLICTS
              if not (REAL_MEMORY / c.relative_path).is_file()]
    assert absent == [], f"recorded placement conflicts no longer on the shelf: {absent}"
